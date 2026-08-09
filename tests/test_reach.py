import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import reach

PROFILE = {
    "needs_sponsorship": True,
    "german_level": "none",
    "target_countries": ["DE", "NL", "IE", "AT", "CH", "GB"],
}


def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat(timespec="seconds")


def job(**overrides):
    base = {
        "title": "Automation Architect",
        "company_name": "Acme",
        "country": "DE",
        "city": "Berlin",
        "remote": "onsite",
        "posted_at": days_ago(3),
        "sponsorship_status": "unknown",
        "language_required": "en",
        "via_agency": 0,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
    }
    base.update(overrides)
    return base


def test_confirmed_sponsorship_scores_far_above_unknown():
    confirmed = reach.compute(job(sponsorship_status="confirmed"), None, PROFILE)
    unknown = reach.compute(job(sponsorship_status="unknown"), None, PROFILE)
    assert confirmed["reach"] > unknown["reach"]
    assert confirmed["factor"] == 1.0
    assert unknown["factor"] == 0.55


def test_denied_sponsorship_collapses_the_score():
    denied = reach.compute(job(sponsorship_status="denied"), None, PROFILE)
    assert denied["reach"] <= 5


def test_a_perfect_job_can_reach_one_hundred():
    best = reach.compute(
        job(
            sponsorship_status="confirmed",
            posted_at=days_ago(1),
            salary_max=90000,
            salary_currency="EUR",
        ),
        None,
        PROFILE,
    )
    assert best["reach"] == 100
    assert best["base"] == 100


def test_german_requirement_costs_everything_when_he_does_not_speak_it():
    with_german = reach.compute(job(language_required="de"), None, PROFILE)
    without = reach.compute(job(language_required="en"), None, PROFILE)
    assert with_german["reach"] < without["reach"]
    fact = [f for f in with_german["facts"] if f["key"] == "language"][0]
    assert fact["points"] == 0 and fact["good"] is False


def test_german_requirement_is_fine_if_he_speaks_german():
    speaks = dict(PROFILE, german_level="c1")
    fact = [
        f for f in reach.compute(job(language_required="de"), None, speaks)["facts"]
        if f["key"] == "language"
    ][0]
    assert fact["good"] is True


def test_agency_postings_score_lower_than_direct_employers():
    agency = reach.compute(job(via_agency=1), None, PROFILE)
    direct = reach.compute(job(via_agency=0), None, PROFILE)
    assert agency["reach"] < direct["reach"]


def test_older_adverts_score_lower():
    fresh = reach.compute(job(posted_at=days_ago(2)), None, PROFILE)
    middling = reach.compute(job(posted_at=days_ago(15)), None, PROFILE)
    old = reach.compute(job(posted_at=days_ago(40)), None, PROFILE)
    stale = reach.compute(job(posted_at=days_ago(200)), None, PROFILE)
    values = [fresh["reach"], middling["reach"], old["reach"], stale["reach"]]
    assert values == sorted(values, reverse=True)


def test_salary_clearing_the_blue_card_threshold_helps():
    over = reach.compute(job(salary_max=60000, salary_currency="EUR"), None, PROFILE)
    under = reach.compute(job(salary_max=30000, salary_currency="EUR"), None, PROFILE)
    silent = reach.compute(job(), None, PROFILE)
    assert over["reach"] > silent["reach"] > under["reach"]


def test_country_outside_targets_scores_zero_for_location():
    fact = [
        f for f in reach.compute(job(country="PL"), None, PROFILE)["facts"]
        if f["key"] == "location"
    ][0]
    assert fact["points"] < fact["max"]


def test_remote_without_a_country_still_scores_something():
    fact = [
        f for f in reach.compute(
            job(country=None, city=None, remote="remote"), None, PROFILE
        )["facts"] if f["key"] == "location"
    ][0]
    assert fact["points"] > 0


def test_not_needing_sponsorship_removes_the_penalty():
    settled = dict(PROFILE, needs_sponsorship=False)
    assert reach.compute(job(), None, settled)["factor"] == 1.0


def test_weights_come_from_config():
    cfg = {"reach": {"factors": {"unknown": 1.0}, "blue_card_eur": 1}}
    result = reach.compute(job(), cfg, PROFILE)
    assert result["factor"] == 1.0


def test_result_is_bounded_and_carries_its_reasons():
    result = reach.compute(job(), None, PROFILE)
    assert 0 <= result["reach"] <= 100
    keys = [f["key"] for f in result["facts"]]
    assert keys[0] == "sponsorship"
    assert set(keys) == {"sponsorship", "language", "employer", "freshness",
                         "location", "salary"}


def test_missing_posted_date_does_not_crash():
    assert reach.compute(job(posted_at=None), None, PROFILE)["reach"] >= 0


def test_no_profile_at_all_still_works():
    assert 0 <= reach.compute(job(), None, None)["reach"] <= 100
