from ...normalize import region_allows, within_days
from ..base import Adapter, get_json

ENDPOINT = "https://remotive.com/api/remote-jobs"


class Remotive(Adapter):
    name = "remotive"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days):
        url = ENDPOINT
        limit = (cfg or {}).get("limit")
        if limit:
            url = url + "?limit=" + str(limit)
        data = get_json(url, timeout=30)
        filter_region = (cfg or {}).get("region_filter", True)

        out = []
        for row in data.get("jobs") or []:
            if not isinstance(row, dict):
                continue
            if filter_region and not region_allows(row.get("candidate_required_location")):
                continue
            if not within_days(row.get("publication_date"), since_days):
                continue
            out.append(
                {
                    "external_id": str(row.get("id")),
                    "url": row.get("url"),
                    "payload": row,
                }
            )
        return out
