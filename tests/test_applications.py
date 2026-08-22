import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import service, store

MASTER = {"identity": {"name": "Alex Morgan"}}
CV_PAYLOAD = {"structured": {"identity": {"name": "Alex Morgan"}, "summary": "", "sections": []}}


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "apps.db"))
    store.init(c)
    src = store.source_id(c, "arbeitnow", "aggregator")
    store.upsert_job(c, {
        "dedup_key": "k1", "title": "Automation Architect", "company_name": "Acme",
        "country": "DE", "url": "https://example.test/1", "description": "Work",
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_ids": [src],
    })
    c.execute("UPDATE job SET gate_status = 'passed'")
    c.commit()
    return c


def test_start_application_creates_a_drafting_row(conn):
    result = service.start_application(conn, 1)
    assert result["status"] == "drafting"
    row = conn.execute("SELECT COUNT(*) AS n FROM application").fetchone()
    assert row["n"] == 1


def test_start_application_is_idempotent(conn):
    service.start_application(conn, 1)
    service.start_application(conn, 1)
    row = conn.execute("SELECT COUNT(*) AS n FROM application").fetchone()
    assert row["n"] == 1


def test_start_application_does_not_clobber_progress(conn):
    service.start_application(conn, 1)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = 1").fetchone()["id"]
    service.set_application_status(conn, app_id, "interview")
    service.start_application(conn, 1)
    status = conn.execute("SELECT status FROM application WHERE job_id = 1").fetchone()
    assert status["status"] == "interview"


def test_start_application_unknown_job_returns_none(conn):
    assert service.start_application(conn, 999) is None


def test_accepting_a_cv_starts_an_application(conn, tmp_path):
    store.save_document(conn, 1, "cv", payload=CV_PAYLOAD)
    result = service.accept_document(conn, 1, "cv", MASTER, str(tmp_path / "docs"))
    assert result["accepted"] is True
    assert result["application_status"] == "drafting"
    row = conn.execute("SELECT status FROM application WHERE job_id = 1").fetchone()
    assert row["status"] == "drafting"


def test_accepting_a_letter_does_not_duplicate_an_existing_application(conn, tmp_path):
    service.start_application(conn, 1)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = 1").fetchone()["id"]
    service.set_application_status(conn, app_id, "applied")

    store.save_document(conn, 1, "letter", body="Dear hiring manager,")
    service.accept_document(conn, 1, "letter", MASTER, str(tmp_path / "docs"))

    rows = conn.execute("SELECT status FROM application WHERE job_id = 1").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "applied"


def test_all_documents_lists_only_accepted_ones(conn, tmp_path):
    store.save_document(conn, 1, "cv", payload=CV_PAYLOAD)
    store.save_document(conn, 1, "letter", body="Dear hiring manager,")
    service.accept_document(conn, 1, "cv", MASTER, str(tmp_path / "docs"))

    docs = service.all_documents(conn)
    assert len(docs) == 1
    assert docs[0]["kind"] == "cv"
    assert docs[0]["company"] == "Acme"
    assert docs[0]["has_file"] is True


def test_all_documents_empty_when_nothing_accepted(conn):
    store.save_document(conn, 1, "cv", payload=CV_PAYLOAD)
    assert service.all_documents(conn) == []


def _old_stamp(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def test_dashboard_window_excludes_old_postings_from_the_new_cards(conn):
    conn.execute("UPDATE job SET posted_at = ?", (_old_stamp(200),))
    conn.commit()
    body = service.dashboard(conn, hours=48)
    values = {c["key"]: c["value"] for c in body["cards"]}
    assert values["New postings"] == 0
    # "Worth a look" is the all-time backlog, not windowed, so it stays 1.
    assert values["Worth a look"] == 1


def test_dashboard_window_includes_recent_postings(conn):
    conn.execute("UPDATE job SET posted_at = ?", (_old_stamp(1),))
    conn.commit()
    body = service.dashboard(conn, hours=48)
    values = {c["key"]: c["value"] for c in body["cards"]}
    assert values["New postings"] == 1
    assert values["Worth a look"] == 1


def test_dashboard_next_actions_use_the_all_time_backlog_not_the_window(conn):
    conn.execute("UPDATE job SET posted_at = ?", (_old_stamp(200),))
    conn.commit()
    body = service.dashboard(conn, hours=48)
    assert any("1 job" in a["text"] for a in body["next_actions"])


def test_job_detail_carries_application_status(conn):
    detail = service.job_detail(conn, 1, MASTER)
    assert detail["application"] is None

    service.start_application(conn, 1)
    detail = service.job_detail(conn, 1, MASTER)
    assert detail["application"]["status"] == "drafting"


def test_dashboard_carries_window_hours_and_last_run(conn):
    store.start_run(conn, ["DE"], 14)
    body = service.dashboard(conn, hours=24)
    assert body["window_hours"] == 24
    assert body["last_run"] is not None


TAILOR_MASTER = {
    "identity": {"name": "Alex Morgan"},
    "experience": [{
        "id": "exp.acme", "company": "Acme", "title": "Engineer",
        "bullets": [{"id": "exp.acme.b1", "text": "Built things.", "skills": []}],
    }],
    "projects": [], "skills": {"core": [], "working": [], "familiar": []},
}


def test_drafting_a_cv_does_not_start_or_advance_an_application(conn, monkeypatch):
    """Generating a CV is a preview, not a decision to apply. Only accepting a
    document (accept_document, the actual save step) should track progress -
    otherwise every job you merely draft a CV for gets silently marked Applied
    before you have looked at it, let alone decided anything."""
    from jobagent.documents import tailor as tailor_module
    monkeypatch.setattr(tailor_module.agent, "run_json", lambda *a, **k: {
        "changes": [{"id": "exp.acme.b1", "action": "kept"}], "note": None,
    })
    service.generate_cv(conn, 1, TAILOR_MASTER)
    assert conn.execute("SELECT COUNT(*) AS n FROM application").fetchone()["n"] == 0


def test_writing_a_letter_does_not_start_or_advance_an_application(conn, monkeypatch):
    from jobagent import documents as documents_module
    monkeypatch.setattr(
        documents_module.tailor.agent, "run_json",
        lambda *a, **k: {"body": "Dear hiring team,", "word_count": 3, "note": None},
    )
    service.generate_letter(conn, 1, MASTER, {})
    assert conn.execute("SELECT COUNT(*) AS n FROM application").fetchone()["n"] == 0


def test_a_cv_drafted_before_saving_leaves_a_manual_drafting_choice_alone(conn):
    """Regression guard: a stale auto-mark used to fire the first time any
    document was generated, overriding whatever the candidate had already set."""
    service.start_application(conn, 1)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = 1").fetchone()["id"]
    service.set_application_status(conn, app_id, "drafting")
    store.save_document(conn, 1, "cv", payload=CV_PAYLOAD)
    status = conn.execute("SELECT status FROM application WHERE job_id = 1").fetchone()
    assert status["status"] == "drafting"


def test_response_mix_splits_drafting_awaiting_and_heard_back(conn):
    service.start_application(conn, 1)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = 1").fetchone()["id"]

    mix = {r["key"]: r["value"] for r in service.applications(conn)["response_mix"]}
    assert mix == {"drafting": 1, "awaiting": 0, "responded": 0}

    service.set_application_status(conn, app_id, "applied")
    mix = {r["key"]: r["value"] for r in service.applications(conn)["response_mix"]}
    assert mix == {"drafting": 0, "awaiting": 1, "responded": 0}

    service.set_application_status(conn, app_id, "interview")
    mix = {r["key"]: r["value"] for r in service.applications(conn)["response_mix"]}
    assert mix == {"drafting": 0, "awaiting": 0, "responded": 1}


def test_response_mix_counts_a_rejection_as_having_heard_back(conn):
    service.start_application(conn, 1)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = 1").fetchone()["id"]
    service.set_application_status(conn, app_id, "rejected")
    mix = {r["key"]: r["value"] for r in service.applications(conn)["response_mix"]}
    assert mix == {"drafting": 0, "awaiting": 0, "responded": 1}
