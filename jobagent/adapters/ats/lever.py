from .board import BoardAdapter

ENDPOINT = "https://api.lever.co/v0/postings/{token}?mode=json"


class Lever(BoardAdapter):
    name = "lever"

    def url_for(self, token):
        return ENDPOINT.format(token=token)

    def rows(self, data):
        return data if isinstance(data, list) else []

    def location_of(self, row):
        return (row.get("categories") or {}).get("location")

    def item(self, row, company):
        url = row.get("hostedUrl") or row.get("applyUrl")
        if not url:
            return None
        row["_company"] = company.get("name")
        return {"external_id": str(row.get("id")), "url": url, "payload": row}
