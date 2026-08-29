import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

DEFAULT_TIMEOUT = 240
DEFAULT_PROVIDER = "claude"

_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)

_CLAUDE_SETUP = {
    "setup_hint": "Install Claude Code and sign in, then this works on your "
                  "existing subscription with no API key.",
    "install_steps": [
        "Open a terminal.",
        "Run: npm install -g @anthropic-ai/claude-code",
        "Run: claude",
        "Type /login and finish signing in in the browser.",
    ],
    "signin_steps": [
        "Open a terminal.",
        "Run: claude",
        "Type /login and finish signing in in the browser.",
        "Come back here and press Check again.",
    ],
    "signin_command": "claude",
}

_CODEX_SETUP = {
    "setup_hint": "Install the Codex CLI (npm install -g @openai/codex) and run "
                  "codex login, then this works on your ChatGPT plan with no "
                  "API key.",
    "install_steps": [
        "Open a terminal.",
        "Run: npm install -g @openai/codex",
        "Run: codex login",
        "Finish signing in in the browser.",
    ],
    "signin_steps": [
        "Open a terminal.",
        "Run: codex login",
        "Finish signing in in the browser.",
        "Come back here and press Check again.",
    ],
    "signin_command": "codex login",
}

PROVIDERS = {
    "claude": dict(_CLAUDE_SETUP, label="Claude (Sonnet)", command="claude",
                   model="claude-sonnet-5"),
    "claude-opus5": dict(_CLAUDE_SETUP, label="Claude (Opus 5)", command="claude",
                         model="claude-opus-5"),
    "openai": dict(_CODEX_SETUP, label="ChatGPT", command="codex"),
}


class AgentError(Exception):
    pass


# The CLIs all fail the same two recoverable ways - not installed, or installed
# but not signed in - and both are things the candidate can fix in a minute.
# Telling them apart here is what lets the app offer the fix instead of showing
# a raw "exited with code 1".
_AUTH_SIGNS = re.compile(
    r"not logged in|/login\b|\blog ?in\b|\bsign ?in\b|unauthori[sz]ed"
    r"|authentication|auth[ _]?error|invalid api key|missing api key"
    r"|oauth|token (?:has )?expired|session (?:has )?expired|\b401\b|\b403\b",
    re.IGNORECASE,
)

# Running out of credit or hitting a rate limit also fails the call, and the
# wording overlaps ("quota", "limit"), but signing in again fixes none of it -
# so those are deliberately not treated as an auth problem.
_NOT_AUTH_SIGNS = re.compile(
    r"credit balance|out of credit|quota|rate limit|usage limit|billing|overloaded",
    re.IGNORECASE,
)


def looks_like_auth_failure(text):
    text = text or ""
    if _NOT_AUTH_SIGNS.search(text):
        return False
    return bool(_AUTH_SIGNS.search(text))


def help_payload(kind, provider, reason=None):
    """Everything the UI needs to walk the candidate through fixing this."""
    info = _provider_info(provider)
    label = info["label"]
    if kind == "missing":
        message = ("The " + info["command"] + " command was not found, so "
                   + label + " cannot be reached.")
        steps = info["install_steps"]
    else:
        message = "You are not signed in to " + label + "."
        steps = info["signin_steps"]
    return {
        "kind": kind,
        "provider": provider,
        "label": label,
        "command": info["command"],
        "signin_command": info["signin_command"],
        "message": message,
        "steps": list(steps),
        "hint": info["setup_hint"],
        "reason": reason,
    }


class AgentSetupError(AgentError):
    """The CLI is missing or not signed in - recoverable, with steps attached."""

    def __init__(self, kind, provider, reason=None):
        self.payload = help_payload(kind, provider, reason)
        self.kind = kind
        self.provider = provider
        super().__init__(self.payload["message"])


def _provider_info(provider):
    info = PROVIDERS.get(provider)
    if not info:
        raise AgentError("Unknown AI provider " + repr(provider))
    return info


def executable(provider=DEFAULT_PROVIDER):
    return shutil.which(_provider_info(provider)["command"])


def available(provider=DEFAULT_PROVIDER):
    return executable(provider) is not None


def _configured_model_claude():
    path = Path.home() / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("model")
    return str(value) if value else None


def _configured_model_codex():
    path = Path.home() / ".codex" / "config.toml"
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = data.get("model")
    return str(value) if value else None


# Resolved at call time, not import time, so the reader can be swapped out.
# Binding the function objects directly here would freeze whichever version
# existed at import, ignoring any later reassignment.
_MODEL_READERS = {
    "claude": lambda: _configured_model_claude(),
    "openai": lambda: _configured_model_codex(),
}


def model(provider=DEFAULT_PROVIDER):
    """Best-effort local read of the model each CLI is configured to use.

    Purely informational (for display) - reads local config files rather than
    spending a real call, so it must never raise or cost anything.
    """
    pinned = PROVIDERS.get(provider, {}).get("model")
    if pinned:
        return pinned
    reader = _MODEL_READERS.get(provider)
    if not reader:
        return None
    try:
        return reader()
    except Exception:
        return None


def _run_claude(exe, prompt, timeout, model=None):
    argv = [exe, "-p"]
    if model:
        argv += ["--model", model]
    argv += ["--output-format", "text"]
    try:
        proc = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise AgentError("Claude took longer than " + str(timeout) + " seconds.")
    except (OSError, UnicodeError) as exc:
        raise AgentError("Could not talk to the claude command. " + str(exc)[:300])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        raise AgentError("Claude exited with code " + str(proc.returncode) + ". " + detail)
    return proc.stdout


def _run_codex(exe, prompt, timeout):
    fd, out_path = tempfile.mkstemp(prefix="jobagent_codex_", suffix=".txt")
    os.close(fd)
    try:
        try:
            proc = subprocess.run(
                [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                 "--output-last-message", out_path, "-"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise AgentError("ChatGPT took longer than " + str(timeout) + " seconds.")
        except (OSError, UnicodeError) as exc:
            raise AgentError("Could not talk to the codex command. " + str(exc)[:300])
        if proc.returncode != 0:
            # codex echoes the whole input prompt back before any error text, so
            # for real (long) prompts the actual reason lives at the end, not the
            # start - take the tail rather than the head.
            detail = (proc.stderr or proc.stdout or "").strip()[-400:]
            raise AgentError(
                "ChatGPT exited with code " + str(proc.returncode) + ". " + detail
            )
        try:
            with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        if not text.strip():
            raise AgentError("ChatGPT did not return a reply.")
        return text
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


_RUNNERS = {"claude": _run_claude, "codex": _run_codex}


def run(prompt, timeout=DEFAULT_TIMEOUT, provider=DEFAULT_PROVIDER):
    info = _provider_info(provider)
    exe = executable(provider)
    if not exe:
        raise AgentSetupError("missing", provider)
    runner = _RUNNERS[info["command"]]
    try:
        if info.get("model"):
            return runner(exe, prompt, timeout, model=info["model"])
        return runner(exe, prompt, timeout)
    except AgentSetupError:
        raise
    except AgentError as exc:
        # The runners report whatever the CLI printed. A sign-in failure hides in
        # there as ordinary text, so it is promoted to something the UI can act on.
        if looks_like_auth_failure(str(exc)):
            raise AgentSetupError("auth", provider, reason=str(exc)) from exc
        raise


def probe(provider=DEFAULT_PROVIDER, timeout=90):
    """Smallest possible real call, used by the "check again" button.

    There is no way to ask either CLI "am I signed in?" without talking to it,
    so this asks for one word and throws away the answer.
    """
    run("Reply with the single word: ok", timeout, provider)
    return True


def run_json(prompt, timeout=DEFAULT_TIMEOUT, provider=DEFAULT_PROVIDER):
    label = _provider_info(provider)["label"]
    raw = run(prompt, timeout, provider).strip()
    match = _FENCE.match(raw)
    if match:
        raw = match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise AgentError(label + " did not return JSON. It said: " + raw[:300])
    try:
        # strict=False tolerates raw control characters (e.g. literal newlines)
        # inside string values, which models sometimes emit despite being
        # asked for JSON.
        return json.loads(raw[start:end + 1], strict=False)
    except ValueError as exc:
        raise AgentError("Could not read " + label + "'s JSON: " + str(exc))
