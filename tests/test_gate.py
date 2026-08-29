import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.gate import evaluate, years_required

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


# ── seniority ──────────────────────────────────────────────────────────────

SENIOR_CFG = dict(CFG, min_years_experience=5)


def _job(description):
    return {
        "title": "Automation Architect",
        "sponsorship_status": "unknown",
        "description": description,
    }


def test_years_required_reads_common_phrasings():
    assert years_required("You have 3+ years of experience in Python") == 3
    assert years_required("Minimum 5 years experience required") == 5
    assert years_required("At least 8 years in a similar role") == 8
    assert years_required("3-5 years of professional experience") == 3
    assert years_required("3 to 5 years of experience") == 3
    assert years_required("10+ yrs of hands-on experience") == 10


def test_years_required_reads_german():
    assert years_required("Mindestens 4 Jahre Berufserfahrung") == 4
    assert years_required("5 Jahre Erfahrung in der Softwareentwicklung") == 5
    assert years_required("Du bringst 2-5 Jahre Berufserfahrung mit") == 2


def test_years_required_takes_the_largest_requirement():
    text = "8+ years of experience overall, plus 2+ years of experience with Kubernetes"
    assert years_required(text) == 8


def test_years_required_ignores_years_that_are_not_a_requirement():
    assert years_required("Our company was founded 10 years ago") is None
    assert years_required("We ship a new release every 2 years") is None
    assert years_required("A senior architect role with broad ownership") is None
    assert years_required("") is None
    assert years_required(None) is None


def test_rejects_role_below_the_experience_floor():
    status, reason = evaluate(_job("We want 3+ years of experience in Python."), SENIOR_CFG)
    assert status == "rejected"
    assert "only 3 years of experience" in reason


def test_reason_reads_naturally_for_a_single_year():
    assert "only 1 year of experience" in evaluate(_job("1+ years of experience."), SENIOR_CFG)[1]


def test_keeps_role_at_or_above_the_floor():
    assert evaluate(_job("8+ years of experience required."), SENIOR_CFG)[0] == "passed"
    assert evaluate(_job("5 years of experience required."), SENIOR_CFG)[0] == "passed"


def test_silent_posting_is_never_treated_as_junior():
    """Most postings never state a number; guessing would drop good roles."""
    assert evaluate(_job("Own our automation platform end to end."), SENIOR_CFG)[0] == "passed"
    assert evaluate(_job(None), SENIOR_CFG)[0] == "passed"


def test_floor_is_off_when_unset():
    assert evaluate(_job("1+ years of experience."), CFG)[0] == "passed"
