import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import service, store

MASTER = {
    "skills": {
        "core": [{"name": "Python"}],
        "working": [{"name": "Docker"}],
        "familiar": [],
    },
    "experience": [
        {
            "id": "exp.acme",
            "company": "Acme",
            "bullets": [
                {"id": "exp.acme.b1", "text": "Led Python automation work.", "skills": []},
                {"id": "exp.acme.b2", "text": "Ran Docker deployments.", "skills": []},
            ],
        },
    ],
}


def _conn(tmp_path):
    conn = store.connect(str(tmp_path / "svc.db"))
    store.init(conn)
    return conn


def _job(conn, i, description, posted_at="2026-08-01T00:00:00+00:00"):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": "k" + str(i), "title": "Role " + str(i), "company_name": "Co" + str(i),
        "country": "DE", "url": "https://example.test/" + str(i),
        "description": description, "posted_at": posted_at, "source_ids": [src],
    })


def test_skill_demand_counts_matching_jobs(tmp_path):
    conn = _conn(tmp_path)
    _job(conn, 1, "We need strong Python skills.")
    _job(conn, 2, "Docker and Python experience required.")
    _job(conn, 3, "Just some unrelated text.")
    ranked = service.skill_demand(conn, MASTER)
    counts = {r["key"]: r["value"] for r in ranked}
    assert counts["Python"] == 2
    assert counts["Docker"] == 1
    conn.close()


def test_skill_demand_handles_no_skills(tmp_path):
    conn = _conn(tmp_path)
    assert service.skill_demand(conn, {"skills": {}}) == []
    conn.close()


def test_profile_freshness_reports_missing_file(tmp_path):
    conn = _conn(tmp_path)
    result = service.profile_freshness(conn, str(tmp_path / "nope.yaml"))
    assert result == {"available": False}
    conn.close()


def test_profile_freshness_counts_jobs_rated_since(tmp_path):
    conn = _conn(tmp_path)
    _job(conn, 1, "desc")
    path = tmp_path / "master.yaml"
    path.write_text("skills: {}\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO score (job_id, profile_version, rubric_version, fit, reach,"
        " scored_at) VALUES (1, 'p', 'r', 50, 50, '2099-01-01T00:00:00+00:00')"
    )
    conn.commit()
    result = service.profile_freshness(conn, str(path))
    assert result["available"] is True
    assert result["jobs_rated_since"] == 1
    conn.close()


def test_bullet_usage_tracks_drops_and_ignores_thin_samples(tmp_path):
    conn = _conn(tmp_path)
    _job(conn, 1, "desc")
    _job(conn, 2, "desc")
    _job(conn, 3, "desc")
    for job_id, changes in [
        (1, [{"id": "exp.acme.b1", "action": "kept"}, {"id": "exp.acme.b2", "action": "dropped"}]),
        (2, [{"id": "exp.acme.b1", "action": "kept"}, {"id": "exp.acme.b2", "action": "dropped"}]),
        (3, [{"id": "exp.acme.b1", "action": "dropped"}]),
    ]:
        store.save_document(conn, job_id, "cv", payload={"changes": changes})
    result = service.bullet_usage(conn, MASTER)
    assert result["documents_considered"] == 3
    by_id = {b["id"]: b for b in result["bullets"]}
    assert by_id["exp.acme.b2"]["drop_rate"] == 100
    assert by_id["exp.acme.b2"]["total"] == 2
    assert by_id["exp.acme.b1"]["total"] == 3
    assert by_id["exp.acme.b1"]["dropped"] == 1
    conn.close()


def test_skill_gaps_cache_round_trip(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    assert service.skill_gaps(conn, MASTER) == {"computed_at": None, "gaps": []}

    _job(conn, 1, "Looking for Rust and WASM experience.", posted_at="2026-08-10T00:00:00+00:00")
    conn.execute("UPDATE job SET gate_status = 'passed'")
    conn.commit()

    monkeypatch.setattr(service.skills_module.agent, "run_json", lambda *a, **k: {
        "gaps": [{"name": "Rust", "note": "mentioned in postings"}],
    })
    result = service.refresh_skill_gaps(conn, MASTER)
    assert result["gaps"] == [{"name": "Rust", "note": "mentioned in postings"}]
    assert result["computed_at"]

    cached = service.skill_gaps(conn, MASTER)
    assert cached == result
    conn.close()


def test_extract_and_save_skills_end_to_end(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(service.skills_module.agent, "run_json", lambda *a, **k: {
        "skills": [{"name": "Kubernetes", "tier": "working", "context": "2 years"}],
    })
    proposed = service.extract_skills(conn, MASTER, "I've used Kubernetes for 2 years")
    assert proposed == [{"name": "Kubernetes", "tier": "working", "context": "2 years"}]

    # master and master_path represent the same on-disk file, as in production
    master_path = tmp_path / "master.yaml"
    master_path.write_text(yaml.safe_dump(MASTER), encoding="utf-8")
    result = service.save_skills(MASTER, str(master_path), proposed)
    assert result["added"] == [{"name": "Kubernetes", "tier": "working"}]
    assert [s["name"] for s in result["tiers"]["working"]] == ["Docker", "Kubernetes"]
    conn.close()


def test_sponsorship_mix_counts_passed_non_applied_jobs(tmp_path):
    conn = _conn(tmp_path)
    for i, status in enumerate(["confirmed", "confirmed", "unknown", "denied"], start=1):
        src = store.source_id(conn, "arbeitnow", "aggregator")
        store.upsert_job(conn, {
            "dedup_key": "k" + str(i), "title": "Role", "company_name": "Co",
            "country": "DE", "url": "https://example.test/" + str(i), "description": "d",
            "posted_at": "2026-08-01T00:00:00+00:00", "source_ids": [src],
            "sponsorship_status": status,
        })
    conn.execute("UPDATE job SET gate_status = 'passed'")
    conn.commit()
    mix = {row["key"]: row["value"] for row in service.sponsorship_mix(conn)}
    assert mix == {"confirmed": 2, "unknown": 1, "denied": 1}
    conn.close()


def test_sponsorship_mix_excludes_applied_jobs(tmp_path):
    conn = _conn(tmp_path)
    _job(conn, 1, "desc")
    conn.execute("UPDATE job SET gate_status = 'passed', sponsorship_status = 'confirmed'")
    conn.execute(
        "INSERT INTO application (job_id, status, applied_at) VALUES"
        " (1, 'applied', '2026-08-01T00:00:00+00:00')"
    )
    conn.commit()
    mix = {row["key"]: row["value"] for row in service.sponsorship_mix(conn)}
    assert mix == {"confirmed": 0, "unknown": 0, "denied": 0}
    conn.close()


def test_keyword_coverage_averages_recent_documents(tmp_path):
    conn = _conn(tmp_path)
    _job(conn, 1, "desc")
    _job(conn, 2, "desc")
    store.save_document(conn, 1, "cv", payload={
        "keywords": {"counts": {"covered": 8, "fixable": 2, "real_gap": 0}},
    })
    store.save_document(conn, 2, "cv", payload={
        "keywords": {"counts": {"covered": 2, "fixable": 2, "real_gap": 6}},
    })
    result = service.keyword_coverage(conn)
    assert result["average"] == 50  # (80 + 20) / 2
    assert len(result["jobs"]) == 2
    assert all("value" in j and "label" in j for j in result["jobs"])
    conn.close()


def test_keyword_coverage_handles_no_documents(tmp_path):
    conn = _conn(tmp_path)
    assert service.keyword_coverage(conn) == {"average": None, "jobs": []}
    conn.close()
