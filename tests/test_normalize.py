import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.normalize import (
    canonical_url,
    detect_agency,
    detect_city,
    detect_country,
    detect_sponsorship,
    fold,
    stable_key,
)


def test_canonical_url_ignores_scheme_www_query_and_slash():
    variants = [
        "https://www.arbeitnow.com/jobs/abc",
        "http://arbeitnow.com/jobs/abc/",
        "https://arbeitnow.com/jobs/abc?utm_source=x",
        "https://arbeitnow.com/jobs/abc#apply",
    ]
    assert len({canonical_url(v) for v in variants}) == 1


def test_stable_key_survives_a_city_change():
    before = stable_key("arbeitnow", "slug-1", "https://x.test/a", "T", "C", "Berlin (Mitte)")
    after = stable_key("arbeitnow", "slug-1", "https://x.test/a", "T", "C", "Berlin")
    assert before == after


def test_stable_key_falls_back_to_external_id():
    a = stable_key("arbeitnow", "slug-1", None, "T", "C", "Berlin")
    b = stable_key("arbeitnow", "slug-1", "", "T", "C", "Munich")
    assert a == b


def test_stable_key_falls_back_to_structure():
    a = stable_key("arbeitnow", None, None, "Title", "Co", "Berlin")
    b = stable_key("arbeitnow", None, None, "Title", "Co", "Berlin")
    assert a == b
    assert a != stable_key("arbeitnow", None, None, "Title", "Co", "Munich")


def test_different_urls_are_different_jobs():
    a = stable_key("arbeitnow", "s1", "https://x.test/a", "T", "C", "Berlin")
    b = stable_key("arbeitnow", "s2", "https://x.test/b", "T", "C", "Berlin")
    assert a != b


def test_plain_german_city():
    assert detect_country("Berlin") == "DE"
    assert detect_city("Berlin") == "Berlin"


def test_umlauts_fold_to_ascii():
    assert fold("Düsseldorf") == "dusseldorf"
    assert fold("München") == "munchen"
    assert fold("Straße") == "strasse"
    assert detect_country("Düsseldorf") == "DE"


def test_explicit_country_name_wins():
    assert detect_country("Munich, Bavaria, Germany") == "DE"
    assert detect_country("Gütersloh, Nordrhein-Westfalen, Deutschland") == "DE"
    assert detect_country("Home Office (Germany)") == "DE"


def test_trailing_country_code():
    assert detect_country("Berlin, DE") == "DE"


def test_uk_maps_to_gb():
    assert detect_country("United Kingdom") == "GB"
    assert detect_country("United Kingdom - London Office") == "GB"
    assert detect_country("London, Mayfair") == "GB"


def test_london_is_not_germany():
    assert detect_country("London") == "GB"


def test_city_found_inside_a_longer_string():
    assert detect_country("LiveEO GmbH Berlin Office (Hybrid)") == "DE"
    assert detect_country("Munich (Hybrid)") == "DE"
    assert detect_country("Berlin (Mitte)") == "DE"


def test_street_address_resolves_by_city():
    assert detect_country("Revaler Strasse 28-31, 10245 Berlin") == "DE"
    assert detect_country("Hinterm Hauptbahnhof 3-5, 76137 Karlsruhe") == "DE"


def test_german_postcode_is_a_fallback_signal():
    assert detect_country("Irgendwo 12, 45678 Kleinstadt") == "DE"


def test_semicolon_and_dash_separate():
    assert detect_country("Oxford; London") == "GB"
    assert detect_country("DE - Berlin") == "DE"


def test_unknown_stays_unknown():
    for value in ["", "remote", "Remote", "Remote job", "EMEA", "Remote-EMEA"]:
        assert detect_country(value) is None, value


def test_out_of_scope_country_is_not_guessed():
    assert detect_country("United States (Remote)") is None


def test_agency_detection():
    assert detect_agency("Hays Recruitment") is True
    assert detect_agency("Zalando SE") is False


def test_sponsorship_confirmed():
    assert detect_sponsorship("This role offers visa sponsorship.") == "confirmed"
    assert detect_sponsorship("We sponsor visas for exceptional candidates.") == "confirmed"


def test_sponsorship_denied_by_direct_phrase():
    assert detect_sponsorship("No visa sponsorship available.") == "denied"


def test_sponsorship_denied_despite_containing_the_yes_phrase():
    assert detect_sponsorship(
        "We are unable to offer visa sponsorship for this role."
    ) == "denied"
    assert detect_sponsorship("We do not sponsor work visas.") == "denied"
    assert detect_sponsorship(
        "Unfortunately we cannot sponsor a visa for this position."
    ) == "denied"


def test_sponsorship_unknown_when_unmentioned():
    assert detect_sponsorship("We are a fast-growing fintech company.") == "unknown"


def test_sponsorship_negation_does_not_misfire_on_a_requirement_clause():
    # "visa sponsorship" still appears literally, so this correctly falls through
    # to the plain keyword match rather than being flagged "denied" by negation.
    assert detect_sponsorship(
        "Preference is given to candidates who do not require visa "
        "sponsorship. However, we are open to candidates who need one."
    ) == "confirmed"
    # Same requirement clause, reworded so no SPONSOR_YES phrase appears literally -
    # this is the real test that negation isn't triggered by "require".
    assert detect_sponsorship(
        "Preference is given to candidates who do not require sponsorship "
        "for a visa. However, we are open to candidates who need one."
    ) == "unknown"


def test_sponsorship_denied_with_an_adverb_before_the_verb():
    assert detect_sponsorship("We do not currently sponsor visas.") == "denied"
