import json
import re
import shutil
import subprocess

DEFAULT_TIMEOUT = 240

_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


class AgentError(Exception):
    pass


def executable():
    return shutil.which("claude")


def available():
    return executable() is not None


def run(prompt, timeout=DEFAULT_TIMEOUT):
    exe = executable()
    if not exe:
        raise AgentError(
            "The claude command was not found. Install Claude Code and sign in, "
            "then this works on your existing subscription with no API key."
        )
    try:
        proc = subprocess.run(
            [exe, "-p", "--output-format", "text"],
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


def run_json(prompt, timeout=DEFAULT_TIMEOUT):
    raw = run(prompt, timeout).strip()
    match = _FENCE.match(raw)
    if match:
        raw = match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise AgentError("Claude did not return JSON. It said: " + raw[:300])
    try:
        return json.loads(raw[start:end + 1])
    except ValueError as exc:
        raise AgentError("Could not read Claude's JSON: " + str(exc))
