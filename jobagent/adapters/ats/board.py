import concurrent.futures

from ...normalize import region_allows
from ..base import Adapter, get_json

# Every company on the watchlist is one independent HTTP call, and the call is
# almost all waiting. Fetched one at a time, 72 companies took over ten minutes
# - not because there is much to download, but because one slow board (Lever
# has been known to take 40-180s to answer) holds up every company behind it.
# Running them together means a run costs about as long as its slowest board
# instead of the sum of all of them.
DEFAULT_WORKERS = 8

# ...and a board that never answers must not be able to hold the run open on
# its own. Whatever has come back by the deadline is what the run uses; the
# stragglers are reported as unreachable and picked up next time.
DEFAULT_DEADLINE = 30


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

    def _shape(self, data, company, token, filter_region):
        """Turn one board's response into postings. No I/O, no shared state."""
        kept = []
        for row in self.rows(data):
            if not isinstance(row, dict):
                continue
            if filter_region and not region_allows(self.location_of(row)):
                continue
            entry = self.item(row, company)
            if entry:
                row["_company"] = company.get("name") or token
                kept.append(entry)
        return kept

    def fetch(self, cfg, countries, since_days):
        settings = cfg or {}
        filter_region = settings.get("region_filter", True)
        timeout = settings.get("timeout_seconds", 12)
        workers = settings.get("workers", DEFAULT_WORKERS)
        deadline = settings.get("deadline_seconds", DEFAULT_DEADLINE)
        self.errors = {}
        self.counts = {}

        targets = [c for c in self.companies if c.get("token")]
        if not targets:
            return []

        def load(company):
            token = company["token"]
            data = get_json(self.url_for(token), timeout=timeout, retries=1)
            return self._shape(data, company, token, filter_region)

        out = []
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(workers, len(targets)))
        )
        try:
            pending = {pool.submit(load, c): c for c in targets}
            done, late = concurrent.futures.wait(pending, timeout=deadline)
            for future in done:
                company = pending[future]
                label = company.get("name") or company["token"]
                try:
                    kept = future.result()
                except Exception as exc:
                    self.errors[label] = type(exc).__name__
                    continue
                out.extend(kept)
                self.counts[label] = len(kept)
            for future in late:
                company = pending[future]
                future.cancel()
                self.errors[company.get("name") or company["token"]] = "TooSlow"
        finally:
            # Never block on the stragglers: their sockets time out on their
            # own, and nothing they return is written anywhere.
            pool.shutdown(wait=False)
        return out
