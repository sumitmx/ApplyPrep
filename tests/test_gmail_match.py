"""Matching a harvested email to an application, and guessing what it means -
the second pass gmail_sync.run() leaves for gmail_match.run() to do, since
nothing here should apply itself without the candidate clicking Apply."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import gmail_match, store


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "match.db"))
    store.init(c)
    return c


def _job_with_application(conn, i, company, status="applied", applied_at=None):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": "k" + str(i), "title": "Role " + str(i), "company_name": company,
        "country": "DE", "url": "https://example.test/" + str(i), "description": "d",
        "posted_at": "2026-08-01T00:00:00+00:00", "source_ids": [src],
    })
    store.start_application(conn, i)
    app_id = conn.execute("SELECT id FROM application WHERE job_id = ?", (i,)).fetchone()["id"]
    conn.execute(
        "UPDATE application SET status = ?, applied_at = ? WHERE id = ?",
        (status, applied_at or "2026-08-01T00:00:00+00:00", app_id),
    )
    conn.commit()
    return app_id


# --- classify ---------------------------------------------------------------

def test_classify_a_rejection():
    assert gmail_match.classify(
        "Update on your application",
        "Unfortunately we will not be moving forward with your application.",
    ) == "rejected"


def test_classify_an_interview_invite():
    assert gmail_match.classify(
        "Next steps", "We would like to invite you to interview with the team.",
    ) == "interview"


def test_classify_a_screening_call():
    assert gmail_match.classify(
        "Quick chat?", "Can we set up a phone screen for next week?",
    ) == "screening"


def test_classify_an_offer():
    assert gmail_match.classify(
        "Great news", "We are pleased to offer you the position.",
    ) == "offer"


def test_classify_a_plain_acknowledgement_is_no_signal():
    assert gmail_match.classify(
        "We received your application", "Thanks for applying, we'll be in touch.",
    ) is None


def test_a_rejection_wins_even_if_it_mentions_interview():
    text = "Thank you for interviewing. Unfortunately we will not be moving forward."
    assert gmail_match.classify("Update", text) == "rejected"


# --- normalize_company -------------------------------------------------------

def test_normalize_company_strips_legal_suffixes():
    assert gmail_match.normalize_company("Acme, Inc.") == "acme"
    assert gmail_match.normalize_company("Vantage Consulting GmbH") == "vantage consulting"


# --- find_application ---------------------------------------------------------

def test_finds_the_application_by_sender_domain(conn):
    app_id = _job_with_application(conn, 1, "Acme")
    found = gmail_match.find_application(conn, "hr@acme.com", "acme.com", "Hi", "")
    assert found == app_id


def test_finds_the_application_by_subject_or_body_text(conn):
    app_id = _job_with_application(conn, 1, "Northwind Labs")
    found = gmail_match.find_application(
        conn, "no-reply@greenhouse.io", "greenhouse.io",
        "Your Northwind Labs application", "",
    )
    assert found == app_id


def test_does_not_match_a_job_never_applied_to(conn):
    _job_with_application(conn, 1, "Acme", status="drafting")
    assert gmail_match.find_application(conn, "hr@acme.com", "acme.com", "", "") is None


def test_does_not_match_an_unrelated_company(conn):
    _job_with_application(conn, 1, "Acme")
    assert gmail_match.find_application(conn, "hr@other.com", "other.com", "Hello", "") is None


def test_a_weak_short_company_name_is_not_guessed_at(conn):
    """A one-word, sub-4-letter name like "Co" would match almost any email -
    skipped rather than risking a false attribution."""
    _job_with_application(conn, 1, "Co")
    found = gmail_match.find_application(conn, "hr@co.com", "co.com", "hello there", "")
    assert found is None


def test_prefers_the_most_recently_applied_when_two_match(conn):
    older = _job_with_application(conn, 1, "Acme", applied_at="2026-07-01T00:00:00+00:00")
    newer = _job_with_application(conn, 2, "Acme", applied_at="2026-08-01T00:00:00+00:00")
    found = gmail_match.find_application(conn, "hr@acme.com", "acme.com", "", "")
    assert found == newer
    assert found != older


# --- run ---------------------------------------------------------------------

def test_run_links_and_classifies_unmatched_emails(conn):
    app_id = _job_with_application(conn, 1, "Acme")
    store.save_application_email(conn, {
        "gmail_message_id": "m1", "sender": "hr@acme.com", "sender_domain": "acme.com",
        "subject": "Update on your application",
        "snippet": "Unfortunately we will not be moving forward.",
    })
    result = gmail_match.run(conn)
    assert result == {"matched": 1, "classified": 1}

    row = conn.execute("SELECT * FROM application_email WHERE gmail_message_id = 'm1'").fetchone()
    assert row["application_id"] == app_id
    assert row["suggested_status"] == "rejected"
    assert row["reviewed"] == 0


def test_run_leaves_an_unmatched_email_alone(conn):
    store.save_application_email(conn, {
        "gmail_message_id": "m2", "sender": "hr@nobody.com", "sender_domain": "nobody.com",
        "subject": "Hello", "snippet": "",
    })
    result = gmail_match.run(conn)
    assert result == {"matched": 0, "classified": 0}
    row = conn.execute("SELECT * FROM application_email WHERE gmail_message_id = 'm2'").fetchone()
    assert row["application_id"] is None


def test_run_is_idempotent_and_does_not_reprocess_matched_rows(conn):
    _job_with_application(conn, 1, "Acme")
    store.save_application_email(conn, {
        "gmail_message_id": "m3", "sender": "hr@acme.com", "sender_domain": "acme.com",
        "subject": "Hi", "snippet": "Thanks for applying.",
    })
    gmail_match.run(conn)
    result = gmail_match.run(conn)
    assert result == {"matched": 0, "classified": 0}
