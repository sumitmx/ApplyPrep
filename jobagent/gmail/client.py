import httpx

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
TIMEOUT = 20
RETRY_STATUS = {429, 500, 502, 503, 504}


def _get(url, access_token, params=None, retries=2):
    headers = {"Authorization": "Bearer " + access_token}
    resp = None
    for attempt in range(retries + 1):
        resp = httpx.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if resp.status_code not in RETRY_STATUS or attempt == retries:
            break
    resp.raise_for_status()
    return resp.json()


def get_profile(access_token):
    return _get(BASE + "/profile", access_token)


def search_messages(access_token, query, max_results=50, page_token=None):
    params = {"q": query, "maxResults": max_results}
    if page_token:
        params["pageToken"] = page_token
    return _get(BASE + "/messages", access_token, params=params)


def get_message(access_token, message_id):
    params = {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]}
    return _get(BASE + "/messages/" + message_id, access_token, params=params)
