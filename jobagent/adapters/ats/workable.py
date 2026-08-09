from .board import BoardAdapter

ENDPOINT = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


class Workable(BoardAdapter):
    name = "workable"

    def url_for(self, token):
        return ENDPOINT.format(token=token)

    def rows(self, data):
        return data.get("jobs") or []

    def location_of(self, row):
        places = row.get("locations") or []
        first = places[0] if places and isinstance(places[0], dict) else {}
        parts = [
            row.get("city") or first.get("city"),
            row.get("country") or first.get("country"),
        ]
        return ", ".join(str(p) for p in parts if p)

    def item(self, row, company):
        url = row.get("url") or row.get("shortlink")
        if not url:
            return None
        row["_company"] = company.get("name")
        return {
            "external_id": str(row.get("shortcode") or row.get("id")),
            "url": url,
            "payload": row,
        }
