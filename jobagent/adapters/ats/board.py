from ...normalize import region_allows
from ..base import Adapter, get_json, pause


class BoardAdapter(Adapter):
    kind = "ats"

    def __init__(self, companies=None):
        self.companies = list(companies or [])
        self.errors = {}
        self.counts = {}

    def url_for(self, token):
        raise NotImplementedError

    def rows(self, data):
        raise NotImplementedError

    def item(self, row, company):
        raise NotImplementedError

    def location_of(self, row):
        return None

    def fetch(self, cfg, countries, since_days):
        settings = cfg or {}
        filter_region = settings.get("region_filter", True)
        gap = settings.get("pause_seconds", 0.4)
        self.errors = {}
        self.counts = {}

        out = []
        for index, company in enumerate(self.companies):
            token = company.get("token")
            if not token:
                continue
            try:
                data = get_json(self.url_for(token), timeout=25)
            except Exception as exc:
                self.errors[company.get("name") or token] = type(exc).__name__
                continue

            kept = 0
            for row in self.rows(data):
                if not isinstance(row, dict):
                    continue
                if filter_region and not region_allows(self.location_of(row)):
                    continue
                entry = self.item(row, company)
                if entry:
                    row["_company"] = company.get("name") or token
                    out.append(entry)
                    kept += 1
            self.counts[company.get("name") or token] = kept
            if index + 1 < len(self.companies):
                pause(gap)
        return out
