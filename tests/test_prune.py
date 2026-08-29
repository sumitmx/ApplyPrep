import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import pull, store

OLD = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
RECENT = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "p.db"))
    store.init(c)
    return c


def _job(conn, key, posted_at, status="new"):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": key,
        "title": "Some role",
        "company_name": "Some Co",
        "url": "https://example.test/" + key,
        "posted_at": posted_at,
        "source_ids": [src],
    })
    row = conn.execute("SELECT id FROM job WHERE dedup_key = ?", (key,)).fetchone()
    job_id = row["id"]
    if status != "new":
        conn.execute("UPDATE job SET status = ? WHERE id = ?", (status, job_id))
        conn.commit()
    return job_id


def test_dry_run_reports_counts_without_deleting(conn):
    _job(conn, "old1", OLD)
    _job(conn, "recent1", RECENT)
    result = pull.prune(conn, days=7, apply=False)
    assert result["eligible"] == 1
    assert result["applied"] is False
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 2


def test_apply_deletes_only_eligible_old_untouched_jobs(conn):
    old_untouched = _job(conn, "old1", OLD)
    _job(conn, "recent1", RECENT)
    result = pull.prune(conn, days=7, apply=True)
    assert result["applied"] is True
    assert result["removed"] == 1
    remaining = {r["dedup_key"] for r in conn.execute("SELECT dedup_key FROM job")}
    assert remaining == {"recent1"}
    assert conn.execute(
        "SELECT 1 FROM job WHERE id = ?", (old_untouched,)
    ).fetchone() is None


def test_shortlisted_jobs_are_protected_regardless_of_age(conn):
    _job(conn, "old-saved", OLD, status="shortlisted")
    result = pull.prune(conn, days=7, apply=True)
    assert result["eligible"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 1


def test_jobs_with_an_application_are_protected(conn):
    old_applied = _job(conn, "old-applied", OLD)
    store.start_application(conn, old_applied)
    result = pull.prune(conn, days=7, apply=True)
    assert result["eligible"] == 0
    assert result["kept_because_referenced"] == 1
    assert conn.execute("SELECT 1 FROM job WHERE id = ?", (old_applied,)).fetchone()


def test_jobs_with_a_saved_document_are_protected(conn):
    old_with_cv = _job(conn, "old-cv", OLD)
    store.save_document(conn, old_with_cv, "cv", payload={"rendered": "x"})
    result = pull.prune(conn, days=7, apply=True)
    assert result["eligible"] == 0
    assert conn.execute("SELECT 1 FROM job WHERE id = ?", (old_with_cv,)).fetchone()


def test_jobs_without_posted_at_are_left_alone(conn):
    _job(conn, "no-date", None)
    result = pull.prune(conn, days=7, apply=True)
    assert result["eligible"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 1


def test_dependent_score_and_reach_rows_are_cleaned_up(conn):
    old_scored = _job(conn, "old-scored", OLD)
    store.upsert_score(conn, {
        "job_id": old_scored, "profile_version": "v1", "rubric_version": "v1",
        "fit": 50, "reach": 50,
    })
    result = pull.prune(conn, days=7, apply=True)
    assert result["removed"] == 1
    assert conn.execute("SELECT 1 FROM score WHERE job_id = ?", (old_scored,)).fetchone() is None


def _empty_pull_cfg(max_age_days):
    """A cfg that pulls nothing (no enabled sources) so run() does no network
    work - only its bookkeeping and the automatic prune afterwards."""
    return {
        "countries": ["DE"],
        "since_days": 7,
        "sources": {},
        "gate": {"max_age_days": max_age_days},
    }


def _stub_pull_inputs(monkeypatch):
    """Keep run() off the filesystem: no profile, master or watchlist files."""
    monkeypatch.setattr(pull, "load_profile", lambda cfg: {})
    monkeypatch.setattr(pull, "sync_watchlist", lambda conn, cfg: [])
    monkeypatch.setattr(pull.profile_module, "load_master", lambda path: None)


def test_pull_prunes_aged_jobs_within_the_gate_window(conn, monkeypatch):
    _stub_pull_inputs(monkeypatch)
    old_untouched = _job(conn, "old1", OLD)
    _job(conn, "recent1", RECENT)

    result = pull.run(conn, _empty_pull_cfg(7))

    assert result["pruned"]["removed"] == 1
    remaining = {r["dedup_key"] for r in conn.execute("SELECT dedup_key FROM job")}
    assert remaining == {"recent1"}
    assert conn.execute("SELECT 1 FROM job WHERE id = ?", (old_untouched,)).fetchone() is None


def test_pull_leaves_everything_when_max_age_is_null(conn, monkeypatch):
    _stub_pull_inputs(monkeypatch)
    _job(conn, "old1", OLD)

    result = pull.run(conn, _empty_pull_cfg(None))

    assert "pruned" not in result
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 1
