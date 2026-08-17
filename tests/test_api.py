import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import api, chat as chat_module, config, store


@pytest.fixture
def client(tmp_path):
    cfg = config.load("does-not-exist.yaml")
    cfg["db_path"] = str(tmp_path / "test.db")
    cfg["master_path"] = str(tmp_path / "master.yaml")
    conn = store.connect(cfg["db_path"])
    store.init(conn)
    seed(conn)
    conn.close()
    tc = TestClient(api.create_app(cfg))
    tc.db_path = cfg["db_path"]
    return tc


def seed(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    posted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, (title, country, sponsorship, mode, agency) in enumerate([
        ("Principal Automation Architect", "DE", "confirmed", "onsite", False),
        ("Lead Platform Architect", "NL", "unknown", "remote", False),
        ("Staff Machine Learning Engineer", "GB", "denied", "onsite", True),
    ], start=1):
        store.upsert_job(conn, {
            "dedup_key": "key" + str(i),
            "title": title,
            "company_name": "Company " + str(i),
            "country": country,
            "city": "City" + str(i),
            "remote": mode,
            "via_agency": agency,
            "url": "https://example.test/" + str(i),
            "description": "We use Python and Terraform.",
            "posted_at": posted_at,
            "sponsorship_status": sponsorship,
            "language_required": "en",
            "source_ids": [src],
        })
    conn.execute(
        "UPDATE job SET gate_status = 'passed' WHERE id IN (1, 2)"
    )
    conn.execute(
        "INSERT INTO score (job_id, profile_version, rubric_version, model, fit,"
        " reach, dimensions, rationale, scored_at, ats_score, offer_probability,"
        " estimate_note) VALUES (1, 'p1', 'r1', 'claude', 84, 79, '{\"core\": 26}',"
        " 'strong match', '2026-08-07T09:00:00+00:00', 78, 62, 'model estimate')"
    )
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO application (job_id, status, applied_at) VALUES (1, 'screening', ?)",
        (stamp,),
    )
    conn.commit()


def test_dashboard(client):
    body = client.get("/api/dashboard").json()
    values = [c["value"] for c in body["cards"]]
    # job 1 has an application, so it's excluded from "New postings" and
    # "Worth a look" too, same as the Jobs list default.
    assert values == [2, 1, 1, 0, 1]
    assert all(c["key"] and c["sub"] for c in body["cards"])
    assert body["gate_counts"]["passed"] == 2
    assert len(body["response_by_band"]) == 2


def test_dashboard_matches_jobs_page_after_hiding(client):
    before = client.get("/api/dashboard").json()
    values_before = {c["key"]: c["value"] for c in before["cards"]}
    # job 1 has an application, so "New postings" excludes it too, same as the
    # Jobs list default.
    assert values_before["New postings"] == 2
    assert values_before["Not rated yet"] == 1

    client.post("/api/jobs/2/mark", json={"action": "hide"})

    after = client.get("/api/dashboard").json()
    values_after = {c["key"]: c["value"] for c in after["cards"]}
    assert values_after["New postings"] == 1
    assert values_after["Not rated yet"] == 0

    window = after["window_hours"]
    everything = client.get("/api/jobs?gate=&hours=" + str(window)).json()
    assert everything["total"] == values_after["New postings"]

    unrated = client.get(
        "/api/jobs?gate=passed&hours=" + str(window) + "&band=unrated"
    ).json()
    assert unrated["total"] == values_after["Not rated yet"]


def test_jobs_list_and_gate_filter(client):
    # job 1 has an application, so it's excluded from the default listing.
    assert client.get("/api/jobs").json()["total"] == 2
    body = client.get("/api/jobs?gate=passed").json()
    assert body["total"] == 1
    assert all(j["gate_status"] == "passed" for j in body["jobs"])


def test_jobs_carry_a_band(client):
    # job 1 has an application, so it no longer shows in the default listing -
    # check its band directly instead.
    assert client.get("/api/jobs/1").json()["band"] == "strong"

    body = client.get("/api/jobs").json()
    bands = {j["id"]: j["band"] for j in body["jobs"]}
    assert bands[2] == "unrated"
    assert [b["key"] for b in body["bands"]] == ["strong", "medium", "unrated", "low"]
    assert body["band_counts"]["unrated"] == 2


def test_band_filter(client):
    body = client.get("/api/jobs?band=unrated").json()
    assert body["total"] == 2
    assert {j["id"] for j in body["jobs"]} == {2, 3}
    assert all(j["band"] == "unrated" for j in body["jobs"])

    # job 1 (the only strong band job) has an application, so ask for it explicitly.
    strong = client.get("/api/jobs?band=strong&applied=1").json()
    assert strong["total"] == 1
    assert strong["jobs"][0]["id"] == 1


def test_band_thresholds():
    from jobagent import service
    assert service.band_for(None, None) == "unrated"
    assert service.band_for(84, 79) == "strong"
    assert service.band_for(84, 20) == "medium"
    assert service.band_for(50, 10) == "medium"
    assert service.band_for(30, 20) == "low"
    assert service.band_for(30, 60) == "medium"


def test_band_thresholds_are_configurable():
    from jobagent import service
    strict = {"strong_match": 90, "strong_chance": 90,
              "medium_match": 85, "medium_chance": 85}
    assert service.band_for(84, 79, strict) == "low"
    assert service.band_for(95, 95, strict) == "strong"

    loose = {"strong_match": 30, "strong_chance": 20,
             "medium_match": 10, "medium_chance": 10}
    assert service.band_for(34, 21, loose) == "strong"


def test_work_mode_filter(client):
    assert client.get("/api/jobs?remote=remote").json()["total"] == 1
    # job 1 is onsite too, but excluded from the default listing (it has an application).
    assert client.get("/api/jobs?remote=onsite").json()["total"] == 1


def test_agency_filter(client):
    # job 1 is a direct employer too, but excluded from the default listing
    # (it has an application).
    assert client.get("/api/jobs?agency=false").json()["total"] == 1
    assert client.get("/api/jobs?agency=true").json()["total"] == 1


def test_sources_breakdown(client):
    b = client.get("/api/sources").json()["breakdown"]
    assert {r["key"]: r["count"] for r in b["work_mode"]} == {"remote": 1, "onsite": 2}
    assert {r["key"]: r["count"] for r in b["country"]}["DE"] == 1
    assert "sponsorship" in b and "language" in b


def test_country_filter(client):
    assert client.get("/api/jobs?country=NL").json()["total"] == 1
    assert client.get("/api/jobs?country=GB").json()["total"] == 1


def test_min_fit_filter(client):
    # job 1 (fit 84) is the only scored job, but it has an application, so ask
    # for it explicitly.
    assert client.get("/api/jobs?min_fit=80&applied=1").json()["total"] == 1
    assert client.get("/api/jobs?min_fit=90&applied=1").json()["total"] == 0


def test_hours_window(client):
    conn = store.connect(client.db_path)
    conn.execute("UPDATE job SET posted_at = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()
    assert client.get("/api/jobs?hours=48").json()["total"] == 0
    # job 1 has an application, so it's excluded from the default listing.
    assert client.get("/api/jobs?hours=100000").json()["total"] == 2


def test_scored_and_unscored_are_distinguishable(client):
    # job 1 has an application, so it no longer shows in the default listing.
    job1 = client.get("/api/jobs/1").json()
    assert job1["scored"] is True
    assert job1["scores"]["fit"] == 84

    jobs = {j["id"]: j for j in client.get("/api/jobs").json()["jobs"]}
    assert jobs[2]["scored"] is False
    assert jobs[2]["scores"]["fit"] is None


def test_estimated_scores_are_labelled(client):
    job = client.get("/api/jobs/1").json()
    assert job["scores"]["ats_score"] == 78
    assert job["scores"]["offer_probability"] == 62
    assert set(job["scores"]["estimated"]) == {"ats_score", "offer_probability"}


def test_job_detail_and_neighbours(client):
    job = client.get("/api/jobs/1").json()
    assert job["dimensions"] == {"core": 26}
    assert job["posted_age"] is not None
    assert "neighbours" in job
    assert client.get("/api/jobs/999").status_code == 404


def test_badges_reflect_facts(client):
    confirmed = client.get("/api/jobs/1").json()["badges"]
    assert any(b["tone"] == "pine" for b in confirmed)

    denied = client.get("/api/jobs/3").json()["badges"]
    tones = [b["tone"] for b in denied]
    assert tones.count("rust") == 2

    assert all(b["text"] and b["tone"] for b in confirmed + denied)


def test_mark_job(client):
    assert client.post("/api/jobs/2/mark", json={"action": "shortlist"}).json()["status"] == "shortlisted"
    assert client.get("/api/jobs?status=shortlisted").json()["total"] == 1
    assert client.post("/api/jobs/2/mark", json={"action": "bogus"}).status_code == 400
    assert client.post("/api/jobs/999/mark", json={"action": "hide"}).status_code == 404


def test_applications_and_status_change(client):
    body = client.get("/api/applications").json()
    assert dict((f["key"], f["value"]) for f in body["funnel"])["screening"] == 1
    assert client.post("/api/applications/1", json={"status": "interview"}).json()["status"] == "interview"
    assert dict((f["key"], f["value"]) for f in client.get("/api/applications").json()["funnel"])["interview"] == 1
    assert client.post("/api/applications/99", json={"status": "offer"}).status_code == 404


def test_sources(client):
    body = client.get("/api/sources").json()
    assert [s["name"] for s in body["sources"]] == ["arbeitnow"]


def test_master_cv_empty_state(client):
    body = client.get("/api/master-cv").json()
    assert body["available"] is False
    assert "master.yaml" in body["hint"]


def test_documents_empty(client):
    body = client.get("/api/documents/1").json()
    assert body["cv"] is None and body["letter"] is None
    assert "agent_available" in body


def test_generate_without_master_yaml_is_refused(client):
    assert client.post("/api/documents/1/cv").status_code == 409
    assert client.post("/api/documents/1/letter").status_code == 409


def test_accept_rejects_unknown_kind(client):
    assert client.post("/api/documents/1/bogus/accept").status_code == 400
    assert client.post("/api/documents/1/cv/accept").status_code == 404


def test_no_scoring_or_tailoring_routes(client):
    assert client.post("/api/score", json={}).status_code in (404, 405)
    assert client.post("/api/tailor", json={}).status_code in (404, 405)


def test_master_cv_uploads_only_offers_cv(client):
    body = client.get("/api/master-cv").json()
    assert set(body["uploads"].keys()) == {"cv"}


def test_master_upload_rejects_letter_kind(client):
    files = {"file": ("resume.txt", b"hello", "text/plain")}
    resp = client.post("/api/master-cv/letter/upload", files=files)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "kind must be cv"


def test_master_cv_preview_is_not_truncated(tmp_path):
    cfg = config.load("does-not-exist.yaml")
    cfg["db_path"] = str(tmp_path / "test.db")
    cfg["master_path"] = str(tmp_path / "master.yaml")
    cfg["documents_dir"] = str(tmp_path / "documents")
    conn = store.connect(cfg["db_path"])
    store.init(conn)
    conn.close()
    tc = TestClient(api.create_app(cfg))

    long_text = "Experienced engineer." + (" Experienced engineer." * 199)
    assert len(long_text) > 1500
    files = {"file": ("resume.txt", long_text.encode("utf-8"), "text/plain")}
    tc.post("/api/master-cv/cv/upload", files=files)

    body = tc.get("/api/master-cv").json()
    preview = body["uploads"]["cv"]["preview"]
    assert preview == long_text
    assert body["uploads"]["cv"]["preview_truncated"] is False


def test_extract_skills_requires_agent(client, monkeypatch):
    monkeypatch.setattr(api.agent, "available", lambda *a, **k: False)
    resp = client.post("/api/skills/extract", json={"text": "I know Python"})
    assert resp.status_code == 503


def test_extract_skills_rejects_empty_text(client):
    resp = client.post("/api/skills/extract", json={"text": "   "})
    assert resp.status_code == 400


def test_save_skills_persists_and_dedups(client):
    resp = client.post("/api/skills", json={
        "skills": [{"name": "Kubernetes", "tier": "working", "context": "2 years"}],
    })
    assert resp.status_code == 200
    assert resp.json()["added"] == [{"name": "Kubernetes", "tier": "working"}]

    again = client.post("/api/skills", json={
        "skills": [{"name": "kubernetes", "tier": "working"}],
    })
    assert again.json()["skipped"] == [{"name": "kubernetes", "reason": "duplicate"}]


def test_save_skills_rejects_empty_list(client):
    assert client.post("/api/skills", json={"skills": []}).status_code == 400


def test_profile_kpis_works_without_master(client):
    body = client.get("/api/profile/kpis").json()
    assert body["skill_demand"] == []
    assert body["freshness"] == {"available": False}
    assert body["bullet_usage"] == {"documents_considered": 0, "bullets": []}


def test_skill_gaps_starts_empty_and_refresh_requires_agent(client, monkeypatch):
    cached = client.get("/api/profile/skill-gaps").json()
    assert cached == {"computed_at": None, "gaps": []}
    monkeypatch.setattr(api.agent, "available", lambda *a, **k: False)
    assert client.post("/api/profile/skill-gaps/refresh").status_code == 503


def test_job_chat_starts_empty(client):
    assert client.get("/api/jobs/1/chat").json() == {"messages": []}


def test_ask_persists_chat_and_is_readable_via_chat_endpoint(client, monkeypatch):
    monkeypatch.setattr(chat_module.agent, "run", lambda *a, **k: "Here is the answer.")

    resp = client.post("/api/jobs/1/ask", json={"question": "What does this role pay?"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Here is the answer."

    chat = client.get("/api/jobs/1/chat").json()["messages"]
    assert chat == [
        {"role": "user", "content": "What does this role pay?"},
        {"role": "assistant", "content": "Here is the answer."},
    ]

    # a second question appends rather than overwriting
    client.post("/api/jobs/1/ask", json={"question": "And the location?"})
    chat = client.get("/api/jobs/1/chat").json()["messages"]
    assert len(chat) == 4
    assert chat[2] == {"role": "user", "content": "And the location?"}


def test_ask_rejects_empty_question(client):
    assert client.post("/api/jobs/1/ask", json={"question": "  "}).status_code == 400
