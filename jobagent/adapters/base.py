import json
import time
import urllib.error
import urllib.request

USER_AGENT = "jobagent/0.1 (personal job search tool)"

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}

DEFAULT_RETRIES = 2
BACKOFF_SECONDS = 2.0


def get_text(url, timeout=20, retries=DEFAULT_RETRIES, headers=None):
    sent = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    sent.update(headers or {})
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=sent)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in RETRY_STATUS:
                raise
        except OSError as exc:
            last = exc
        if attempt < retries:
            time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise last


def get_json(url, timeout=20, retries=DEFAULT_RETRIES, headers=None):
    return json.loads(get_text(url, timeout=timeout, retries=retries, headers=headers))


def pause(seconds):
    if seconds and seconds > 0:
        time.sleep(seconds)


class Adapter:
    name = "base"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days):
        raise NotImplementedError
