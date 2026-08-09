import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import service, store


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "score.db"))
    store.init(c)
    src = store.source_id(c, "arbeitnow", "aggregator")
    for i in range(1, 4):
        store.upsert_job(c, {
            "dedup_key": "k" + str(i),
            "title": "Automation Architect " + str(i),
            "company_name": "Co" + str(i),
            "country": "DE",
            "url": "https://example.test/" + str(i),
            "description": "Python, Terraform, Kubernetes.",
            "posted_at": "2026-08-07T00:00:00+00:00",
            "source_ids": [src],
        })
    c.execute("UPDATE job SET gate_status = 'passed'")
    c.commit()
    return c


def test_requirements_section_finds_a_plain_requirements_heading():
    text = (
        "About the Role\nWe build things.\n"
        "Requirements\n- Python\n- Terraform\n"
        "Benefits\n- Remote work\n"
    )
    out = service.requirements_section(text)
    assert out.startswith("Requirements")
    assert "Python" in out and "Terraform" in out
    assert "Remote work" not in out


def test_requirements_section_stops_at_responsibilities_not_requirements():
    text = "Requirements\n- Python\nResponsibilities\n- Ship code\n"
    out = service.requirements_section(text)
    assert "Ship code" not in out


def test_requirements_section_keeps_related_subheadings():
    text = (
        "Requirements\n\nQualifications / Experience / Technical Skills\n"
        "- Ten years of Python\nSoft Skills\n- Communication\n"
    )
    out = service.requirements_section(text)
    assert "Qualifications / Experience / Technical Skills" in out
    assert "Ten years of Python" in out
    assert "Soft Skills" in out
    assert "Communication" in out


def test_requirements_section_matches_what_were_looking_for():
    text = "About the Role\nWe do things.\nWhat We're Looking For\nRequired\n- Python\n"
    out = service.requirements_section(text)
    assert out.startswith("What We're Looking For")
    assert "Python" in out


def test_requirements_section_drops_empty_bullet_artifacts():
    text = "Requirements:\n\n-\n\n- Python\n"
    out = service.requirements_section(text)
    assert "- Python" in out
    assert "\n-\n" not in out


def test_requirements_section_returns_none_when_nothing_matches():
    text = "We are a friendly team building nice things for people everywhere.\n"
    assert service.requirements_section(text) is None


def test_requirements_section_handles_nothing():
    assert service.requirements_section(None) is None
    assert service.requirements_section("") is None


def test_shape_job_falls_back_to_full_description_with_a_flag(conn):
    conn.execute(
        "UPDATE job SET description = ? WHERE id = 1",
        ("Just a plain paragraph with no clear section headings at all here.",),
    )
    conn.commit()
    row = service.jobs(conn, gate="passed")["jobs"]
    job = [j for j in row if j["id"] == 1][0]
    assert job["requirements_found"] is False
    assert job["requirements"].startswith("Just a plain paragraph")


def test_shape_job_carries_requirements_and_saved_flag(conn):
    conn.execute(
        "UPDATE job SET description = ? WHERE id = 1",
        ("About the role\nWe build things.\nRequirements\n- Python\n- Kubernetes\n",),
    )
    conn.execute("UPDATE job SET status = 'shortlisted' WHERE id = 1")
    conn.commit()
    saved = service.jobs(conn, status="shortlisted")["jobs"]
    assert saved[0]["id"] == 1
    assert saved[0]["saved"] is True
    assert saved[0]["requirements_found"] is True
    assert saved[0]["requirements"].startswith("Requirements")

    others = service.jobs(conn, gate="passed")["jobs"]
    other = [j for j in others if j["id"] != 1][0]
    assert other["saved"] is False


def test_pending_lists_unscored_passed_jobs(conn):
    assert len(service.pending_jobs(conn)) == 3
    assert service.pending_count(conn) == 3


def test_pending_puts_sponsoring_jobs_first(conn):
    conn.execute("UPDATE job SET sponsorship_status = 'unknown'")
    conn.execute("UPDATE job SET sponsorship_status = 'confirmed' WHERE id = 3")
    conn.execute("UPDATE job SET sponsorship_status = 'denied' WHERE id = 1")
    conn.commit()
    assert [j["id"] for j in service.pending_jobs(conn)] == [3, 2, 1]


def test_pending_prefers_direct_employers_over_agencies(conn):
    conn.execute("UPDATE job SET sponsorship_status = 'confirmed'")
    conn.execute("UPDATE job SET via_agency = 1 WHERE id = 1")
    conn.commit()
    assert service.pending_jobs(conn)[-1]["id"] == 1


def test_save_score_then_it_leaves_pending(conn):
    service.save_score(conn, 1, fit=84, reach=79)
    ids = [j["id"] for j in service.pending_jobs(conn)]
    assert 1 not in ids and len(ids) == 2


def test_saved_score_appears_on_the_job(conn):
    service.save_score(conn, 1, fit=84, reach=79, dimensions={"core": 26},
                       rationale="strong", ats_score=78, offer_probability=62,
                       estimate_note="model estimate")
    job = service.job_detail(conn, 1)
    assert job["scores"]["fit"] == 84
    assert job["scores"]["ats_score"] == 78
    assert job["scores"]["offer_probability"] == 62
    assert job["dimensions"] == {"core": 26}
    assert job["scored"] is True


def test_rescoring_updates_rather_than_duplicates(conn):
    service.save_score(conn, 1, fit=50, reach=50)
    service.save_score(conn, 1, fit=90, reach=70)
    assert conn.execute("SELECT COUNT(*) n FROM score").fetchone()["n"] == 1
    assert service.job_detail(conn, 1)["scores"]["fit"] == 90


def test_scores_must_be_in_range(conn):
    with pytest.raises(ValueError):
        service.save_score(conn, 1, fit=140, reach=50)
    with pytest.raises(ValueError):
        service.save_score(conn, 1, fit=50, reach=-1)
    with pytest.raises(ValueError):
        service.save_score(conn, 1, fit=50, reach=50, ats_score=101)


def test_save_scores_reports_unknown_ids(conn):
    result = service.save_scores(conn, [
        {"job_id": 1, "fit": 80, "reach": 70},
        {"job_id": 999, "fit": 80, "reach": 70},
    ])
    assert len(result["saved"]) == 1
    assert result["unknown_job_ids"] == [999]


def test_top_jobs_orders_by_fit(conn):
    service.save_scores(conn, [
        {"job_id": 1, "fit": 60, "reach": 90},
        {"job_id": 2, "fit": 88, "reach": 40},
        {"job_id": 3, "fit": 75, "reach": 75},
    ])
    assert [j["id"] for j in service.top_jobs(conn)] == [2, 3, 1]
    assert [j["id"] for j in service.top_jobs(conn, min_fit=70)] == [2, 3]


def test_fit_and_reach_are_never_blended(conn):
    service.save_score(conn, 1, fit=88, reach=20)
    scores = service.job_detail(conn, 1)["scores"]
    assert scores["fit"] == 88 and scores["reach"] == 20
    assert "overall" not in scores and "combined" not in scores


def test_mark_many_batches(conn):
    result = service.mark_many(conn, [
        {"job_id": 1, "action": "shortlist"},
        {"job_id": 2, "action": "hide"},
        {"job_id": 999, "action": "hide"},
    ])
    assert len(result["marked"]) == 2
    assert result["unknown_job_ids"] == [999]


def test_hidden_jobs_drop_out_of_pending(conn):
    service.mark_job(conn, 1, "hide")
    assert 1 not in [j["id"] for j in service.pending_jobs(conn)]


def test_job_brief_truncates_long_descriptions(conn):
    conn.execute("UPDATE job SET description = ? WHERE id = 1", ("x" * 9000,))
    conn.commit()
    brief = service.job_brief(conn, 1, description_chars=100)
    assert len(brief["description"]) == 100
    assert brief["description_truncated"] is True
    assert service.job_brief(conn, 999) is None
