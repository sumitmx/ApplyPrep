from datetime import datetime, timedelta, timezone

from . import store
from .gmail import auth, client

ATS_DOMAINS = ["greenhouse.io", "lever.co", "ashbyhq.com", "workable.com"]
KEYWORDS = ["application", "applied", "interview", '"thank you for applying"']


def _build_query(lookback_days):
    after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    domain_terms = ["from:(" + domain + ")" for domain in ATS_DOMAINS]
    keyword_terms = ["subject:(" + kw + ")" for kw in KEYWORDS]
    return "after:" + after + " (" + " OR ".join(domain_terms + keyword_terms) + ")"


def _header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _sender_domain(sender):
    if not sender or "@" not in sender:
        return None
    return sender.rsplit("@", 1)[-1].strip("> ").lower()


def _received_at(message):
    internal = message.get("internalDate")
    if not internal:
        return None
    try:
        return datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError):
        return None


def run(conn, cfg):
    gcfg = cfg.get("gmail") or {}
    sync_id = store.start_gmail_sync(conn)

    try:
        client_id, client_secret = auth.resolve_client(
            conn, gcfg.get("client_secret_path", "gmail_client_secret.json")
        )
        access_token = auth.get_valid_access_token(conn, client_id, client_secret)
    except auth.GmailAuthError as exc:
        status = "reconnect_required" if isinstance(exc, auth.ReconnectRequired) else "not_connected"
        store.finish_gmail_sync(conn, sync_id, 0, 0, {"status": status, "error": str(exc)})
        return {"status": status, "scanned": 0, "stored": 0, "error": str(exc)}

    query = _build_query(gcfg.get("lookback_days", 90))
    known = store.known_gmail_message_ids(conn)

    scanned = 0
    stored = 0
    page_token = None
    detail = {"query": query}

    try:
        while True:
            page = client.search_messages(access_token, query, page_token=page_token)
            for stub in page.get("messages") or []:
                scanned += 1
                if stub["id"] in known:
                    continue
                full = client.get_message(access_token, stub["id"])
                headers = full.get("payload", {}).get("headers") or []
                sender = _header(headers, "From")
                store.save_application_email(conn, {
                    "application_id": None,
                    "gmail_message_id": full["id"],
                    "gmail_thread_id": full.get("threadId"),
                    "subject": _header(headers, "Subject"),
                    "sender": sender,
                    "sender_domain": _sender_domain(sender),
                    "snippet": full.get("snippet"),
                    "received_at": _received_at(full),
                })
                known.add(full["id"])
                stored += 1
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:
        detail["error"] = str(exc)

    store.finish_gmail_sync(conn, sync_id, scanned, stored, detail)
    return {"status": "ok", "scanned": scanned, "stored": stored, "sync_id": sync_id}
