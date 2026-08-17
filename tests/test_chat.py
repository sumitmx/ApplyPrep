import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import chat as chat_module, service, store

MASTER = {"skills": {"core": [], "working": [], "familiar": []}}


def _conn(tmp_path):
    conn = store.connect(str(tmp_path / "chat.db"))
    store.init(conn)
    return conn


def _job(conn, i=1):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": "k" + str(i), "title": "Role " + str(i), "company_name": "Co",
        "country": "DE", "url": "https://example.test/" + str(i),
        "description": "We build things.", "posted_at": "2026-08-01T00:00:00+00:00",
        "source_ids": [src],
    })


def test_get_chat_defaults_to_empty(tmp_path):
    conn = _conn(tmp_path)
    assert store.get_chat(conn, 1) == []
    conn.close()


def test_save_chat_round_trips_and_overwrites(tmp_path):
    conn = _conn(tmp_path)
    _job(conn)
    store.save_chat(conn, 1, [{"role": "user", "content": "hi"}])
    assert store.get_chat(conn, 1) == [{"role": "user", "content": "hi"}]
    store.save_chat(conn, 1, [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    assert store.get_chat(conn, 1) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    conn.close()


def test_ask_about_job_persists_across_calls(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _job(conn)
    replies = iter(["First answer", "Second answer"])
    monkeypatch.setattr(chat_module.agent, "run", lambda *a, **k: next(replies))

    answer1 = service.ask_about_job(conn, 1, MASTER, "What is this role?")
    assert answer1 == "First answer"
    assert store.get_chat(conn, 1) == [
        {"role": "user", "content": "What is this role?"},
        {"role": "assistant", "content": "First answer"},
    ]

    answer2 = service.ask_about_job(conn, 1, MASTER, "Anything else?")
    assert answer2 == "Second answer"
    assert store.get_chat(conn, 1) == [
        {"role": "user", "content": "What is this role?"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Anything else?"},
        {"role": "assistant", "content": "Second answer"},
    ]
    assert service.job_chat(conn, 1) == store.get_chat(conn, 1)
    conn.close()


def test_ask_about_job_returns_none_for_missing_job(tmp_path):
    conn = _conn(tmp_path)
    assert service.ask_about_job(conn, 999, MASTER, "hi") is None
    conn.close()
