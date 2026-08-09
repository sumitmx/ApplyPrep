import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.gate import evaluate

CFG = {
    "title_must_match": ["architect", "automation"],
    "title_must_not_match": ["intern", "working student"],
    "max_age_days": 45,
    "allow_contract": True,
    "min_salary_eur": None,
    "require_english_only": False,
}


def test_passes_relevant_title():
    job = {"title": "Principal Automation Architect", "sponsorship_status": "confirmed"}
    assert evaluate(job, CFG)[0] == "passed"


def test_rejects_excluded_title():
    job = {"title": "Working Student Data", "sponsorship_status": "unknown"}
    status, reason = evaluate(job, CFG)
    assert status == "rejected"
    assert "working student" in reason


def test_rejects_denied_sponsorship():
    job = {"title": "Automation Architect", "sponsorship_status": "denied"}
    assert evaluate(job, CFG)[0] == "rejected"


def test_unknown_sponsorship_survives():
    job = {"title": "Automation Architect", "sponsorship_status": "unknown"}
    assert evaluate(job, CFG)[0] == "passed"


def test_german_not_rejected_by_default():
    job = {
        "title": "Automation Architect",
        "sponsorship_status": "unknown",
        "language_required": "de",
    }
    assert evaluate(job, CFG)[0] == "passed"


SPONSOR_CFG = dict(CFG, sponsor_bypass_title=True)


def test_sponsoring_job_survives_a_title_miss():
    job = {"title": "Backend Engineer", "sponsorship_status": "confirmed"}
    status, reason = evaluate(job, SPONSOR_CFG)
    assert status == "passed"
    assert "sponsors visas" in reason


def test_non_sponsoring_job_still_needs_the_title():
    job = {"title": "Backend Engineer", "sponsorship_status": "unknown"}
    assert evaluate(job, SPONSOR_CFG)[0] == "rejected"


def test_sponsorship_never_rescues_a_junior_title():
    job = {"title": "Working Student Backend", "sponsorship_status": "confirmed"}
    status, reason = evaluate(job, SPONSOR_CFG)
    assert status == "rejected"
    assert "working student" in reason


def test_sponsorship_never_rescues_a_stale_posting():
    job = {
        "title": "Backend Engineer",
        "sponsorship_status": "confirmed",
        "posted_at": "2020-01-01T00:00:00+00:00",
    }
    assert evaluate(job, SPONSOR_CFG)[0] == "rejected"


def test_bypass_can_be_switched_off():
    strict = dict(CFG, sponsor_bypass_title=False)
    job = {"title": "Backend Engineer", "sponsorship_status": "confirmed"}
    assert evaluate(job, strict)[0] == "rejected"


def test_matching_title_passes_without_a_bypass_reason():
    job = {"title": "Automation Architect", "sponsorship_status": "confirmed"}
    assert evaluate(job, SPONSOR_CFG) == ("passed", None)


RPA_CFG = dict(CFG, title_must_match=["rpa", "architect"])


def test_rpa_does_not_match_inside_german_compound():
    job = {
        "title": "Schichtleiter / Teamleiter Verpackung (m/w/d)",
        "sponsorship_status": "unknown",
    }
    status, reason = evaluate(job, RPA_CFG)
    assert status == "rejected"
    assert reason == "title matched no target keyword"


def test_rpa_matches_as_a_standalone_word():
    job = {"title": "RPA Solution Architect", "sponsorship_status": "unknown"}
    assert evaluate(job, RPA_CFG)[0] == "passed"


def test_hyphen_and_slash_count_as_separators():
    cfg = dict(CFG, title_must_match=["ai engineer"])
    for title in ["AI Engineer", "AI-Engineer", "AI/Engineer"]:
        job = {"title": title, "sponsorship_status": "unknown"}
        assert evaluate(job, cfg)[0] == "passed", title


def test_exclusion_does_not_match_inside_a_word():
    cfg = dict(CFG, title_must_not_match=["intern"], title_must_match=["architect"])
    job = {"title": "International Solutions Architect", "sponsorship_status": "unknown"}
    assert evaluate(job, cfg)[0] == "passed"


MASTER = {
    "skills": {
        "core": [{"name": "RPA"}, {"name": "UiPath"}],
        "working": [{"name": "Python"}],
        "familiar": [{"name": "Kubernetes"}],
    }
}


def test_sponsor_bypass_needs_skill_overlap_when_master_given():
    job = {
        "title": "Legal Counsel",
        "sponsorship_status": "confirmed",
        "description": "We need a lawyer with contract experience.",
    }
    status, reason = evaluate(job, SPONSOR_CFG, MASTER)
    assert status == "rejected"
    assert "skills did not match" in reason


def test_sponsor_bypass_survives_when_skills_overlap():
    job = {
        "title": "Automation Engineer",
        "sponsorship_status": "confirmed",
        "description": "Hands-on RPA delivery using UiPath across the business.",
    }
    status, reason = evaluate(job, SPONSOR_CFG, MASTER)
    assert status == "passed"


def test_sponsor_bypass_unaffected_without_master():
    job = {"title": "Legal Counsel", "sponsorship_status": "confirmed"}
    status, reason = evaluate(job, SPONSOR_CFG)
    assert status == "passed"


GENERIC_CFG = dict(
    CFG,
    title_must_match=["architect", "automation", "software engineer"],
    title_generic_keywords=["software engineer"],
)


def test_generic_title_keyword_needs_skill_overlap_when_master_given():
    job = {
        "title": "Software Engineer - Distributed Compute",
        "sponsorship_status": "unknown",
        "description": "Strong C++ expertise, quantitative trading systems, low latency.",
    }
    status, reason = evaluate(job, GENERIC_CFG, MASTER)
    assert status == "rejected"
    assert "not enough matching skills" in reason


def test_generic_title_keyword_passes_with_skill_overlap():
    job = {
        "title": "Software Engineer - Automation Platform",
        "sponsorship_status": "unknown",
        "description": "Building RPA workflows with UiPath and Python.",
    }
    assert evaluate(job, GENERIC_CFG, MASTER)[0] == "passed"


def test_specific_title_keyword_unaffected_without_master():
    job = {
        "title": "Software Engineer - Distributed Compute",
        "sponsorship_status": "unknown",
        "description": "Strong C++ expertise, quantitative trading systems.",
    }
    assert evaluate(job, GENERIC_CFG)[0] == "passed"


def test_zero_max_age_still_rejects_stale():
    cfg = dict(CFG, max_age_days=0)
    job = {
        "title": "Automation Architect",
        "sponsorship_status": "unknown",
        "posted_at": "2020-01-01T00:00:00+00:00",
    }
    status, reason = evaluate(job, cfg)
    assert status == "rejected"
    assert "stale" in reason
