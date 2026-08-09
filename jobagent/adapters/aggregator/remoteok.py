from ...normalize import region_allows, within_days
from ..base import Adapter, get_json

ENDPOINT = "https://remoteok.com/api"


class RemoteOK(Adapter):
    name = "remoteok"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days):
        data = get_json(ENDPOINT, timeout=30)
        if not isinstance(data, list):
            return []
        filter_region = (cfg or {}).get("region_filter", True)

        out = []
        for row in data:
            if not isinstance(row, dict):
                continue
            if row.get("legal") or not row.get("id"):
                continue
            if filter_region and not region_allows(row.get("location")):
                continue
            if not within_days(row.get("date") or row.get("epoch"), since_days):
                continue
            out.append(
                {
                    "external_id": str(row.get("id")),
                    "url": row.get("url") or row.get("apply_url"),
                    "payload": row,
                }
            )
        return out
