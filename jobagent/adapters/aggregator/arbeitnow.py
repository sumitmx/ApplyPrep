from ..base import Adapter, get_json

ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"


class Arbeitnow(Adapter):
    name = "arbeitnow"
    kind = "aggregator"

    def fetch(self, cfg, countries, since_days, pages=3):
        out = []
        for page in range(1, pages + 1):
            data = get_json(ENDPOINT + "?page=" + str(page))
            rows = data.get("data", [])
            if not rows:
                break
            for row in rows:
                out.append(
                    {
                        "external_id": row.get("slug"),
                        "url": row.get("url"),
                        "payload": row,
                    }
                )
        return out
