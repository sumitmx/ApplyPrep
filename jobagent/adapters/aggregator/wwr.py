import concurrent.futures
from xml.etree import ElementTree

from ...normalize import region_allows, within_days
from ..base import Adapter, get_text

FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
]


def _settle(call, arg):
    """Run one fetch and hand back (rows, error) instead of raising.

    A pool worker that raises would lose every other feed's result, and one
    dead category is not a reason to lose the other three.
    """
    try:
        return call(arg), None
    except Exception as exc:
        return [], type(exc).__name__


def parse_feed(body):
    root = ElementTree.fromstring(body)
    rows = []
    for item in root.findall("./channel/item"):
        row = {}
        for child in item:
            tag = child.tag.split("}")[-1]
            row[tag] = (child.text or "").strip()
        if row:
            rows.append(row)
    return rows


class WeWorkRemotely(Adapter):
    name = "wwr"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days):
        settings = cfg or {}
        feeds = settings.get("feeds") or FEEDS
        filter_region = settings.get("region_filter", True)

        seen = set()
        out = []
        self.errors = {}

        # The four category feeds have nothing to do with each other, so there
        # is no reason to wait for one before asking for the next. Results are
        # still walked in feed order below, so de-duplication stays predictable.
        def load(feed):
            return parse_feed(get_text(feed, timeout=30))

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(feeds)) as pool:
            fetched = list(zip(feeds, pool.map(
                lambda f: _settle(load, f), feeds
            )))

        for feed, (rows, error) in fetched:
            if error is not None:
                self.errors[feed] = error
                continue
            for row in rows:
                link = row.get("link") or row.get("guid")
                if not link or link in seen:
                    continue
                if filter_region and not region_allows(row.get("region")):
                    continue
                if not within_days(row.get("pubDate"), since_days):
                    continue
                seen.add(link)
                out.append({"external_id": row.get("guid") or link, "url": link, "payload": row})
        return out
