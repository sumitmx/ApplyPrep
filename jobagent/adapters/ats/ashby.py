from .board import BoardAdapter

ENDPOINT = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


class Ashby(BoardAdapter):
    name = "ashby"

    def url_for(self, token):
        return ENDPOINT.format(token=token)

    def rows(self, data):
        return data.get("jobs") or []

    def location_of(self, row):
        return row.get("location")

    def item(self, row, company):
        if row.get("isListed") is False:
            return None
        url = row.get("jobUrl") or row.get("applyUrl")
        if not url:
            return None
        row["_company"] = company.get("name")
        return {"external_id": str(row.get("id")), "url": url, "payload": row}
