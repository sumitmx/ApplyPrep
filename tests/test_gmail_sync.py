import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import gmail_sync, store
from jobagent.gmail import auth

BASE_CFG = {"gmail": {"client_secret_path": "unused.json", "lookback_days": 90}}

MESSAGE = {
    "id": "msg1",
    "threadId": "thread1",
    "snippet": "Thanks for applying to Acme",
    "internalDate": "1700000000000",
    "payload": {"headers": [
        {"name": "Subject", "value": "Thanks for applying"},
        {"name": "From", "value": "Acme Careers <no-reply@greenhouse.io>"},
        {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
    ]},
}


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "gmail.db"))
    store.init(c)
    return c


def _connected(monkeypatch):
    monkeypatch.setattr(auth, "load_client_secret", lambda path: ("id", "secret"))
    monkeypatch.setattr(auth, "get_valid_access_token", lambda conn, cid, secret: "token")


def test_save_application_email_is_idempotent_at_the_store_level(conn):
    message = {"gmail_message_id": "dup1", "subject": "Hi"}
    store.save_application_email(conn, message)
    store.save_application_email(conn, message)
    count = conn.execute("SELECT COUNT(*) AS n FROM application_email").fetchone()["n"]
    assert count == 1


def test_not_connected_reports_status_without_raising(conn, monkeypatch):
    monkeypatch.setattr(auth, "load_client_secret", lambda path: ("id", "secret"))

    def boom(conn, cid, secret):
        raise auth.NotConnected("not connected")

    monkeypatch.setattr(auth, "get_valid_access_token", boom)

    result = gmail_sync.run(conn, BASE_CFG)
    assert result["status"] == "not_connected"
    row = conn.execute("SELECT * FROM gmail_sync_log").fetchone()
    assert row["finished_at"] is not None


def test_reconnect_required_reports_status_without_raising(conn, monkeypatch):
    monkeypatch.setattr(auth, "load_client_secret", lambda path: ("id", "secret"))

    def boom(conn, cid, secret):
        raise auth.ReconnectRequired("expired")

    monkeypatch.setattr(auth, "get_valid_access_token", boom)

    result = gmail_sync.run(conn, BASE_CFG)
    assert result["status"] == "reconnect_required"


def test_sync_stores_new_messages(conn, monkeypatch):
    _connected(monkeypatch)
    monkeypatch.setattr(
        gmail_sync.client, "search_messages",
        lambda token, query, page_token=None: {"messages": [{"id": "msg1", "threadId": "thread1"}]},
    )
    monkeypatch.setattr(gmail_sync.client, "get_message", lambda token, mid: MESSAGE)

    result = gmail_sync.run(conn, BASE_CFG)
    assert result["status"] == "ok"
    assert result["scanned"] == 1
    assert result["stored"] == 1

    row = conn.execute("SELECT * FROM application_email").fetchone()
    assert row["gmail_message_id"] == "msg1"
    assert row["application_id"] is None
    assert row["sender_domain"] == "greenhouse.io"
    assert row["subject"] == "Thanks for applying"

    log = conn.execute("SELECT * FROM gmail_sync_log ORDER BY id DESC LIMIT 1").fetchone()
    assert log["messages_scanned"] == 1
    assert log["stored_count"] == 1
    assert log["finished_at"] is not None


def test_sync_is_idempotent_on_rerun(conn, monkeypatch):
    _connected(monkeypatch)
    monkeypatch.setattr(
        gmail_sync.client, "search_messages",
        lambda token, query, page_token=None: {"messages": [{"id": "msg1", "threadId": "thread1"}]},
    )
    get_message_calls = []

    def get_message(token, mid):
        get_message_calls.append(mid)
        return MESSAGE

    monkeypatch.setattr(gmail_sync.client, "get_message", get_message)

    gmail_sync.run(conn, BASE_CFG)
    result = gmail_sync.run(conn, BASE_CFG)

    assert result["scanned"] == 1
    assert result["stored"] == 0
    assert get_message_calls == ["msg1"]
    count = conn.execute("SELECT COUNT(*) AS n FROM application_email").fetchone()["n"]
    assert count == 1


def test_sync_paginates_through_results(conn, monkeypatch):
    _connected(monkeypatch)
    pages = {
        None: {"messages": [{"id": "msg1", "threadId": "t1"}], "nextPageToken": "p2"},
        "p2": {"messages": [{"id": "msg2", "threadId": "t2"}]},
    }
    monkeypatch.setattr(
        gmail_sync.client, "search_messages",
        lambda token, query, page_token=None: pages[page_token],
    )
    monkeypatch.setattr(
        gmail_sync.client, "get_message",
        lambda token, mid: dict(MESSAGE, id=mid, threadId=mid),
    )

    result = gmail_sync.run(conn, BASE_CFG)
    assert result["scanned"] == 2
    assert result["stored"] == 2
