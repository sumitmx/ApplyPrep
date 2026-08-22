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

PROVIDERS = {
    "claude": {
        "label": "Claude (Sonnet)",
        "command": "claude",
        "model": "claude-sonnet-5",
        "setup_hint": "Install Claude Code and sign in, then this works on your "
                       "existing subscription with no API key.",
    },
    "claude-opus5": {
        "label": "Claude (Opus 5)",
        "command": "claude",
        "model": "claude-opus-5",
        "setup_hint": "Install Claude Code and sign in, then this works on your "
                       "existing subscription with no API key.",
    },
    "openai": {
        "label": "ChatGPT",
        "command": "codex",
        "setup_hint": "Install the Codex CLI (npm install -g @openai/codex) and run "
                       "codex login, then this works on your ChatGPT plan with no "
                       "API key.",
    },
}


class AgentError(Exception):
    pass


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
        raise AgentError(
            "The " + info["command"] + " command was not found. " + info["setup_hint"]
        )
    runner = _RUNNERS[info["command"]]
    if info.get("model"):
        return runner(exe, prompt, timeout, model=info["model"])
    return runner(exe, prompt, timeout)


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
