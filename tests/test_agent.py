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
