import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import agent, rating, service, store

LIMITS = {"strong_match": 70, "strong_chance": 50,
          "medium_match": 45, "medium_chance": 45}

MASTER = {
    "identity": {"name": "Alex Morgan", "title": "Principal Architect"},
    "skills": {
        "core": [{"name": "Python", "context": "12 yr"}],
        "working": [{"name": "Terraform"}],
        "familiar": [{"name": "Django", "context": "read the code, never shipped"}],
    },
    "experience": [
        {"title": "Principal Architect", "company": "Acme",
         "bullets": [{"id": "b1", "text": "Built an automation platform"}]}
    ],
}

PROFILE = {"seniority": "principal", "base": "Lisbon, India",
           "needs_sponsorship": True, "german_level": "none"}

JOB = {
    "id": 1, "title": "Automation Architect", "company": "Globex",
    "city": "Berlin", "country": "DE", "remote": "hybrid",
    "employment_type": "full time", "language": "en",
    "sponsorship": "confirmed", "salary": {"min": None, "max": None},
    "description": "Design automation platforms.",
}


def test_the_claude_call_sends_utf8_so_symbols_do_not_crash(monkeypatch):
    seen = {}

    class Done:
        returncode = 0
        stdout = '{"fit": 50}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        kwargs["input"].encode(kwargs["encoding"])
        return Done()

    monkeypatch.setattr(agent.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    advert = "Salary " + chr(8805) + " 90k " + chr(8594) + " apply " + chr(127908)
    agent.run(advert)
    assert seen["encoding"] == "utf-8"


def test_a_job_advert_full_of_symbols_can_be_scored(monkeypatch):
    class Done:
        returncode = 0
        stdout = '{"fit": 55, "rationale": "ok"}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        kwargs["input"].encode(kwargs["encoding"])
        return Done()

    monkeypatch.setattr(agent.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    job = dict(JOB, description="Must have " + chr(8805) + "10 years " + chr(127908))
    assert rating.score(job, MASTER, PROFILE, 40, LIMITS)["fit"] == 55


def test_dimensions_are_summed_into_fit():
    result = rating.clean({
        "dimensions": {"core_technical": 25, "seniority_scope": 18, "domain": 12,
                       "logistics": 15, "compensation": 6, "signal": 4},
        "fit": 3,
        "rationale": "Strong overlap.",
    }, False)
    assert result["fit"] == 80


def test_dimensions_are_capped_at_their_rubric_weight():
    result = rating.clean({
        "dimensions": {"core_technical": 999, "seniority_scope": 0, "domain": 0,
                       "logistics": 0, "compensation": 0, "signal": 0},
    }, False)
    assert result["dimensions"]["core_technical"] == 30
    assert result["fit"] == 30


def test_fit_is_used_when_dimensions_are_incomplete():
    result = rating.clean({"fit": 64, "dimensions": {"core_technical": 20}}, False)
    assert result["fit"] == 64


def test_missing_fit_is_an_error():
    with pytest.raises(agent.AgentError):
        rating.clean({"rationale": "no numbers here"}, False)


def test_estimates_are_dropped_below_the_strong_band():
    result = rating.clean({"fit": 50, "ats_score": 90, "offer_probability": 80}, False)
    assert result["ats_score"] is None
    assert result["offer_probability"] is None
    assert result["estimate_note"] is None


def test_estimates_are_kept_in_the_strong_band_and_always_labelled():
    result = rating.clean({"fit": 80, "ats_score": 90, "offer_probability": 60}, True)
    assert result["ats_score"] == 90
    assert result["offer_probability"] == 60
    assert result["estimate_note"]


def test_a_returned_reach_is_ignored():
    assert "reach" not in rating.clean({"fit": 70, "reach": 99}, False)


def test_out_of_range_values_are_clamped():
    result = rating.clean({"fit": 500}, False)
    assert result["fit"] == 100


def test_prompt_tells_the_model_not_to_return_reach():
    prompt = rating.build_prompt(JOB, MASTER, PROFILE, 61, True)
    assert "Do NOT return reach" in prompt
    assert "61 out of 100 for reach" in prompt


def test_prompt_switches_the_estimate_instruction_on_the_band():
    on = rating.build_prompt(JOB, MASTER, PROFILE, 80, True)
    off = rating.build_prompt(JOB, MASTER, PROFILE, 20, False)
    assert "also fill ats_score" in on
    assert "Leave ats_score" in off


def test_prompt_carries_the_skill_tiers_and_their_honesty_labels():
    prompt = rating.build_prompt(JOB, MASTER, PROFILE, 50, False)
    assert "Python (12 yr)" in prompt
    assert "read the code, never shipped" in prompt
    assert "Needs visa sponsorship: yes" in prompt


def test_score_drops_estimates_when_fit_misses_the_bar(monkeypatch):
    monkeypatch.setattr(
        rating.agent, "run_json",
        lambda prompt, timeout: {"fit": 40, "ats_score": 88, "offer_probability": 70},
    )
    result = rating.score(JOB, MASTER, PROFILE, 90, LIMITS)
    assert result["fit"] == 40
    assert result["ats_score"] is None


def test_rate_job_saves_fit_and_leaves_reach_computed(tmp_path, monkeypatch):
    conn = store.connect(str(tmp_path / "rate.db"))
    store.init(conn)
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": "k1", "title": "Automation Architect", "company_name": "Globex",
        "country": "DE", "url": "https://example.test/1", "description": "Work",
        "posted_at": "2026-08-08T00:00:00+00:00", "source_ids": [src],
    })
    store.save_reach(conn, 1, {"reach": 61, "base": 92, "factor": 0.55,
                               "sponsorship": "unknown", "facts": []})

    monkeypatch.setattr(
        rating.agent, "run_json",
        lambda prompt, timeout: {
            "fit": 72,
            "dimensions": {"core_technical": 24, "seniority_scope": 16, "domain": 11,
                           "logistics": 14, "compensation": 5, "signal": 2},
            "rationale": "Good overlap on automation.",
            "reach": 95,
        },
    )
    result = service.rate_job(conn, 1, MASTER, PROFILE, LIMITS)
    assert result["scores"]["fit"] == 72
    assert result["scores"]["reach"] == 61
    assert result["scores"]["reach_source"] == "computed"
    assert result["band"] == "strong"
    conn.close()


def test_clean_estimate_reads_the_value():
    result = rating.clean_estimate({"value": 62, "note": "a guess"})
    assert result == {"value": 62, "note": "a guess"}


def test_clean_estimate_labels_itself_when_no_note_given():
    result = rating.clean_estimate({"value": 40})
    assert "estimate" in result["note"].lower()


def test_clean_estimate_rejects_a_missing_value():
    with pytest.raises(agent.AgentError):
        rating.clean_estimate({"note": "no number here"})


def test_estimate_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        rating.estimate(JOB, MASTER, PROFILE, 80, "why", 60, "bogus")


def test_build_estimate_prompt_carries_the_existing_fit_and_reach():
    prompt = rating.build_estimate_prompt(JOB, MASTER, PROFILE, 72, "solid overlap", 61, "ats")
    assert "72 out of 100" in prompt
    assert "61" in prompt
    assert "solid overlap" in prompt


def test_estimate_ats_and_offer_ask_different_questions():
    ats_prompt = rating.build_estimate_prompt(JOB, MASTER, PROFILE, 72, "x", 61, "ats")
    offer_prompt = rating.build_estimate_prompt(JOB, MASTER, PROFILE, 72, "x", 61, "offer")
    assert "resume-screening" in ats_prompt
    assert "leads to an offer" in offer_prompt


def _rated_conn(tmp_path):
    conn = store.connect(str(tmp_path / "estimate.db"))
    store.init(conn)
    src = store.source_id(conn, "arbeitnow", "aggregator")
    store.upsert_job(conn, {
        "dedup_key": "k1", "title": "Automation Architect", "company_name": "Globex",
        "country": "DE", "url": "https://example.test/1", "description": "Work",
        "posted_at": "2026-08-08T00:00:00+00:00", "source_ids": [src],
    })
    store.save_reach(conn, 1, {"reach": 61, "base": 92, "factor": 0.55,
                               "sponsorship": "unknown", "facts": []})
    return conn


def test_rate_estimate_needs_an_existing_score_first(tmp_path):
    conn = _rated_conn(tmp_path)
    with pytest.raises(service.NotRatedError):
        service.rate_estimate(conn, 1, MASTER, PROFILE, "ats")
    conn.close()


def test_rate_estimate_updates_only_the_requested_field(tmp_path, monkeypatch):
    conn = _rated_conn(tmp_path)
    service.save_score(conn, 1, fit=72, reach=61, rationale="Good overlap.")

    monkeypatch.setattr(
        rating.agent, "run_json",
        lambda prompt, timeout: {"value": 88, "note": "an estimate"},
    )
    result = service.rate_estimate(conn, 1, MASTER, PROFILE, "ats")
    assert result["scores"]["ats_score"] == 88
    assert result["scores"]["offer_probability"] is None
    assert result["scores"]["fit"] == 72

    monkeypatch.setattr(
        rating.agent, "run_json",
        lambda prompt, timeout: {"value": 55, "note": "another estimate"},
    )
    result = service.rate_estimate(conn, 1, MASTER, PROFILE, "offer")
    assert result["scores"]["offer_probability"] == 55
    assert result["scores"]["ats_score"] == 88
    assert result["scores"]["fit"] == 72
    conn.close()


def test_rate_estimate_unknown_job_returns_none(tmp_path):
    conn = _rated_conn(tmp_path)
    service.save_score(conn, 1, fit=72, reach=61)
    assert service.rate_estimate(conn, 999, MASTER, PROFILE, "ats") is None
    conn.close()
