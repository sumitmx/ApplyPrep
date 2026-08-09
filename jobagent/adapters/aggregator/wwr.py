from xml.etree import ElementTree

from ...normalize import region_allows, within_days
from ..base import Adapter, get_text, pause

FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
]


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
        gap = settings.get("pause_seconds", 0.5)

        seen = set()
        out = []
        self.errors = {}
        for index, feed in enumerate(feeds):
            try:
                body = get_text(feed, timeout=30)
                rows = parse_feed(body)
            except Exception as exc:
                self.errors[feed] = type(exc).__name__
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
            if index + 1 < len(feeds):
                pause(gap)
        return out
