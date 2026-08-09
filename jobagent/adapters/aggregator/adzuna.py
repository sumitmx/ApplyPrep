from urllib.parse import urlencode

from ..base import Adapter, get_json, pause

ENDPOINT = "https://api.adzuna.com/v1/api/jobs/"

SUPPORTED = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb",
    "in", "it", "mx", "nl", "nz", "pl", "sg", "us", "za",
}

DEFAULT_QUERIES = [
    "automation architect",
    "solution architect",
    "ai engineer",
    "platform engineer",
    "rpa",
]


class Adzuna(Adapter):
    name = "adzuna"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days):
        settings = cfg or {}
        app_id = settings.get("app_id")
        app_key = settings.get("app_key")
        self.errors = {}
        if not app_id or not app_key:
            self.errors["credentials"] = "app_id and app_key are not set"
            return []

        queries = settings.get("queries") or DEFAULT_QUERIES
        max_pages = int(settings.get("max_pages", 1))
        per_page = int(settings.get("results_per_page", 50))
        gap = settings.get("pause_seconds", 0.5)
        codes = [c.lower() for c in (countries or []) if c.lower() in SUPPORTED]

        out = []
        calls = 0
        for code in codes:
            for what in queries:
                for page in range(1, max_pages + 1):
                    params = {
                        "app_id": app_id,
                        "app_key": app_key,
                        "results_per_page": per_page,
                        "what": what,
                        "content-type": "application/json",
                        "sort_by": "date",
                    }
                    if since_days:
                        params["max_days_old"] = since_days
                    url = ENDPOINT + code + "/search/" + str(page) + "?" + urlencode(params)
                    try:
                        data = get_json(url, timeout=30)
                    except Exception as exc:
                        self.errors[code + "/" + what] = type(exc).__name__
                        break
                    calls += 1
                    rows = data.get("results") or []
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        row["_country"] = code
                        out.append(
                            {
                                "external_id": str(row.get("id")),
                                "url": row.get("redirect_url"),
                                "payload": row,
                            }
                        )
                    if len(rows) < per_page:
                        break
                    pause(gap)
        self.calls = calls
        return out
