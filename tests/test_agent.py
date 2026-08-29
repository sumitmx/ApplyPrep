import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import agent


class _FakeProc:
    def __init__(self, argv):
        self.argv = argv
        self.returncode = 0
        self.stdout = "ok"
        self.stderr = ""


@pytest.fixture
def capture_argv(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeProc(argv)

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent, "executable", lambda provider=agent.DEFAULT_PROVIDER: "claude")
    return calls


def test_plain_claude_is_pinned_to_sonnet(capture_argv):
    agent.run("hello", provider="claude")
    assert capture_argv[0] == [
        "claude", "-p", "--model", "claude-sonnet-5", "--output-format", "text",
    ]


def test_claude_opus5_adds_model_flag(capture_argv):
    agent.run("hello", provider="claude-opus5")
    assert capture_argv[0] == ["claude", "-p", "--model", "claude-opus-5", "--output-format", "text"]


def test_codex_argv_is_unchanged(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        Path(argv[6]).write_text("some reply", encoding="utf-8")
        return _FakeProc(argv)

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent, "executable", lambda provider=agent.DEFAULT_PROVIDER: "codex")

    agent.run("hello", provider="openai")
    argv = calls[0]
    assert argv[0] == "codex"
    assert argv[1:6] == [
        "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--output-last-message",
    ]
    assert argv[7] == "-"
    assert "jobagent_codex_" in argv[6]


def test_codex_failure_surfaces_the_tail_not_the_echoed_prompt(monkeypatch):
    def fake_run(argv, **kwargs):
        proc = _FakeProc(argv)
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = ("prompt echo " * 50) + "ERROR: You've hit your usage limit."
        return proc

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent, "executable", lambda provider=agent.DEFAULT_PROVIDER: "codex")

    with pytest.raises(agent.AgentError) as exc:
        agent.run("hello", provider="openai")
    assert "You've hit your usage limit" in str(exc.value)


def test_model_shows_pinned_model_for_opus5():
    assert agent.model("claude-opus5") == "claude-opus-5"


def test_model_reports_the_pinned_sonnet_for_plain_claude(monkeypatch):
    """Plain "Claude" is pinned to Sonnet, so the local-config reader is never
    consulted for it - the pin always wins."""
    monkeypatch.setattr(agent, "_configured_model_claude", lambda: "some-other-model")
    assert agent.model("claude") == "claude-sonnet-5"


def test_run_json_tolerates_a_raw_newline_inside_a_string(monkeypatch):
    """Models sometimes emit a literal newline inside a JSON string value
    instead of an escaped \\n. Strict json.loads rejects that as an invalid
    control character; run_json must still parse it."""
    def fake_run(argv, **kwargs):
        proc = _FakeProc(argv)
        proc.stdout = '{"body": "line one\nline two"}'
        return proc

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent, "executable", lambda provider=agent.DEFAULT_PROVIDER: "claude")

    result = agent.run_json("hello", provider="claude")
    assert result == {"body": "line one\nline two"}


# ── sign-in failures ───────────────────────────────────────────────────────
# A CLI that is missing or signed out is the one failure the candidate can fix
# themselves, so it has to arrive as something the UI can build a dialog from
# rather than a sentence.


@pytest.mark.parametrize("text", [
    "Claude exited with code 1. Not logged in · Please run /login",
    "codex: error: not logged in, run codex login",
    "401 Unauthorized",
    "OAuth token has expired",
    "Invalid API key provided",
])
def test_auth_failures_are_recognised(text):
    assert agent.looks_like_auth_failure(text)


@pytest.mark.parametrize("text", [
    "Your credit balance is too low to continue",
    "rate limit exceeded, try again later",
    "usage limit reached",
    "Claude took longer than 240 seconds.",
    "Claude exited with code 1. Segmentation fault",
])
def test_billing_and_plain_failures_are_not_auth(text):
    """Signing in again fixes none of these, so they must not offer to."""
    assert not agent.looks_like_auth_failure(text)


def _fail_with(monkeypatch, message):
    def boom(exe, prompt, timeout, model=None):
        raise agent.AgentError(message)
    monkeypatch.setitem(agent._RUNNERS, "claude", boom)
    monkeypatch.setattr(agent.shutil, "which", lambda cmd: "/usr/bin/" + cmd)


def test_signed_out_run_raises_a_setup_error_with_steps(monkeypatch):
    _fail_with(monkeypatch, "Claude exited with code 1. Not logged in - Please run /login")
    with pytest.raises(agent.AgentSetupError) as caught:
        agent.run("hello", provider="claude")
    payload = caught.value.payload
    assert payload["kind"] == "auth"
    assert payload["provider"] == "claude"
    assert payload["steps"]
    assert "Not logged in" in payload["reason"]


def test_ordinary_failure_stays_an_ordinary_error(monkeypatch):
    _fail_with(monkeypatch, "Claude exited with code 1. Segmentation fault")
    with pytest.raises(agent.AgentError) as caught:
        agent.run("hello", provider="claude")
    assert not isinstance(caught.value, agent.AgentSetupError)


def test_missing_command_is_a_setup_error_with_install_steps(monkeypatch):
    monkeypatch.setattr(agent.shutil, "which", lambda cmd: None)
    with pytest.raises(agent.AgentSetupError) as caught:
        agent.run("hello", provider="claude")
    payload = caught.value.payload
    assert payload["kind"] == "missing"
    assert any("install" in step.lower() for step in payload["steps"])


def test_every_provider_can_describe_how_to_fix_itself():
    for key in agent.PROVIDERS:
        for kind in ("auth", "missing"):
            payload = agent.help_payload(kind, key)
            assert payload["steps"] and payload["label"] and payload["message"]
