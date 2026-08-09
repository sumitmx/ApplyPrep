from .board import BoardAdapter

ENDPOINT = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class Greenhouse(BoardAdapter):
    name = "greenhouse"

    def url_for(self, token):
        return ENDPOINT.format(token=token)

    def rows(self, data):
        return data.get("jobs") or []

    def location_of(self, row):
        return (row.get("location") or {}).get("name")

    def item(self, row, company):
        url = row.get("absolute_url")
        if not url:
            return None
        row["_company"] = company.get("name")
        return {"external_id": str(row.get("id")), "url": url, "payload": row}
