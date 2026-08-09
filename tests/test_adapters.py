import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import watchlist
from jobagent.adapters.aggregator.wwr import parse_feed
from jobagent.normalize import (
    clean_line,
    normalize,
    parse_stamp,
    region_allows,
    repair_text,
    split_wwr_title,
    strip_html,
)


def wrap(payload, external_id=None, url=None):
    return {"external_id": external_id, "url": url, "payload": payload}


def test_strip_html_unescapes_then_removes_tags():
    escaped = "&lt;p&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;br&gt;We are hiring&lt;/p&gt;"
    assert strip_html(escaped) == "About\nWe are hiring"


def test_strip_html_turns_list_items_into_lines():
    assert "- Python" in strip_html("<ul><li>Python</li><li>Terraform</li></ul>")


def test_strip_html_drops_script_bodies():
    assert "alert" not in strip_html("<div>Role<script>alert(1)</script></div>")


def test_repair_text_fixes_double_encoded_utf8():
    broken = "Mr. Xi" + chr(226) + chr(128) + chr(153) + "s plan"
    assert repair_text(broken) == "Mr. Xi" + chr(8217) + "s plan"


def test_repair_text_leaves_clean_text_alone():
    assert repair_text("plain ascii") == "plain ascii"


def test_parse_stamp_handles_every_shape_the_sources_send():
    assert parse_stamp("2026-08-07T01:10:06").startswith("2026-08-07T01:10:06")
    assert parse_stamp(1782498827119).startswith("2026-")
    assert parse_stamp("Wed, 22 Jul 2026 07:01:32 +0000").startswith("2026-07-22")
    assert parse_stamp("2025-12-17").startswith("2025-12-17")
    assert parse_stamp(None) is None
    assert parse_stamp("") is None


def test_region_allows_keeps_europe_and_worldwide():
    for value in ["Europe", "EMEA", "Worldwide", "Anywhere in the World",
                  "Europe, EMEA, UK, Germany, France", "Berlin, Germany",
                  "Americas, Europe, Israel", ""]:
        assert region_allows(value) is True, value


def test_region_allows_rejects_stated_non_european_places():
    for value in ["USA", "USA, Canada, USA timezones", "Anupgarh, ",
                  "Austin, United States", "India"]:
        assert region_allows(value) is False, value


def test_clean_line_collapses_whitespace():
    assert clean_line("  AFC Analyst - Spanish Market  ") == "AFC Analyst - Spanish Market"


def test_split_wwr_title_separates_company_from_role():
    assert split_wwr_title("Airtable: Manager, Sales Strategy") == (
        "Airtable", "Manager, Sales Strategy"
    )
    assert split_wwr_title("No colon here") == ("", "No colon here")


def test_arbeitnow_strips_html_from_the_description():
    job = normalize("arbeitnow", wrap({
        "title": "Junior Product Designer",
        "company_name": "Clera",
        "location": "Munich, Germany",
        "description": (
            '<h3>About the Role</h3><p style="min-height:1.5em">We are hiring.'
            "</p><ul><li>Figma</li><li>Design systems</li></ul>"
        ),
        "tags": ["design"],
    }, "1", "https://arbeitnow.com/jobs/1"), 1)
    assert "<" not in job["description"]
    assert "About the Role" in job["description"]
    assert "- Figma" in job["description"]


def test_remotive_mapping():
    job = normalize("remotive", wrap({
        "id": 2091045,
        "url": "https://remotive.com/remote-jobs/x-2091045",
        "title": "Automation Architect",
        "company_name": "Unio Digital",
        "tags": ["azure", "python"],
        "job_type": "full_time",
        "publication_date": "2026-08-07T01:10:06",
        "candidate_required_location": "Europe",
        "description": "<p>Build things</p>",
    }, "2091045", "https://remotive.com/remote-jobs/x-2091045"), 1)
    assert job["title"] == "Automation Architect"
    assert job["company_name"] == "Unio Digital"
    assert job["remote"] == "remote"
    assert job["description"] == "Build things"
    assert job["employment_type"] == "full_time"
    assert job["posted_at"].startswith("2026-08-07")


def test_remoteok_treats_zero_salary_as_unknown():
    job = normalize("remoteok", wrap({
        "id": "1136327",
        "position": "Platform Engineer",
        "company": "CHINADebate",
        "location": "Berlin",
        "description": "Work",
        "date": "2026-08-08T05:28:17+00:00",
        "url": "https://remoteOK.com/remote-jobs/x-1136327",
        "salary_min": 0,
        "salary_max": 0,
        "tags": ["exec"],
    }, "1136327", "https://remoteOK.com/remote-jobs/x-1136327"), 1)
    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert job["salary_currency"] is None
    assert job["country"] == "DE"


def test_remoteok_keeps_a_real_salary():
    job = normalize("remoteok", wrap({
        "id": "1", "position": "Architect", "company": "Co", "location": "Europe",
        "description": "x", "url": "https://remoteok.com/1",
        "salary_min": 90000, "salary_max": 120000,
    }, "1", "https://remoteok.com/1"), 1)
    assert (job["salary_min"], job["salary_max"], job["salary_currency"]) == (
        90000, 120000, "USD"
    )


def test_wwr_mapping_and_worldwide_has_no_city():
    job = normalize("wwr", wrap({
        "title": "Airtable: Staff Engineer",
        "region": "Anywhere in the World",
        "category": "Full-Stack Programming",
        "description": "<p>Remote role</p>",
        "pubDate": "Wed, 22 Jul 2026 07:01:32 +0000",
        "link": "https://weworkremotely.com/remote-jobs/airtable-staff",
    }, None, "https://weworkremotely.com/remote-jobs/airtable-staff"), 1)
    assert job["company_name"] == "Airtable"
    assert job["title"] == "Staff Engineer"
    assert job["city"] is None
    assert job["country"] is None
    assert job["remote"] == "remote"


def test_adzuna_drops_a_predicted_salary():
    payload = {
        "id": "5", "title": "Solution Architect",
        "company": {"display_name": "Acme"},
        "location": {"area": ["Germany", "Berlin"], "display_name": "Berlin"},
        "description": "Role", "created": "2026-08-01T10:00:00Z",
        "redirect_url": "https://adzuna.test/5",
        "salary_min": 60000, "salary_max": 80000, "salary_is_predicted": "1",
        "_country": "de",
    }
    job = normalize("adzuna", wrap(payload, "5", "https://adzuna.test/5"), 1)
    assert job["salary_min"] is None and job["salary_currency"] is None
    assert job["country"] == "DE"


def test_adzuna_keeps_a_published_salary_with_country_currency():
    payload = {
        "id": "6", "title": "Architect", "company": {"display_name": "Acme"},
        "location": {"area": ["United Kingdom", "London"]},
        "description": "Role", "created": "2026-08-01T10:00:00Z",
        "redirect_url": "https://adzuna.test/6",
        "salary_min": 70000, "salary_max": 90000, "salary_is_predicted": "0",
        "_country": "gb",
    }
    job = normalize("adzuna", wrap(payload, "6", "https://adzuna.test/6"), 1)
    assert job["salary_max"] == 90000
    assert job["salary_currency"] == "GBP"
    assert job["country"] == "GB"


def test_greenhouse_mapping_uses_watchlist_company():
    job = normalize("greenhouse", wrap({
        "id": 8105089,
        "title": "Principal Engineer ",
        "location": {"name": "Berlin "},
        "absolute_url": "https://n26.com/careers/8105089",
        "content": "&lt;p&gt;We sponsor visas&lt;/p&gt;",
        "first_published": "2026-08-06T05:24:34-04:00",
        "_company": "N26",
    }, "8105089", "https://n26.com/careers/8105089"), 1)
    assert job["company_name"] == "N26"
    assert job["title"] == "Principal Engineer"
    assert job["city"] == "Berlin"
    assert job["description"] == "We sponsor visas"
    assert job["sponsorship_status"] == "confirmed"


def test_lever_mapping_reads_ms_epoch_and_salary_range():
    job = normalize("lever", wrap({
        "id": "f2ab14ed",
        "text": "Staff Engineer",
        "categories": {"commitment": "Full Time", "location": "Amsterdam",
                       "department": "Engineering", "team": "Core"},
        "hostedUrl": "https://jobs.lever.co/aircall/f2ab14ed",
        "createdAt": 1782498827119,
        "descriptionPlain": "Build the platform",
        "salaryRange": {"min": 70000, "max": 95000, "currency": "EUR",
                        "interval": "per-year-salary"},
        "workplaceType": "remote",
        "_company": "Aircall",
    }, "f2ab14ed", "https://jobs.lever.co/aircall/f2ab14ed"), 1)
    assert job["company_name"] == "Aircall"
    assert job["country"] == "NL"
    assert job["remote"] == "remote"
    assert job["salary_max"] == 95000 and job["salary_currency"] == "EUR"
    assert job["posted_at"].startswith("2026-")


def test_ashby_mapping():
    job = normalize("ashby", wrap({
        "id": "89fb70ec",
        "title": "Engineering Manager - EU",
        "location": "Remote",
        "employmentType": "FullTime",
        "publishedAt": "2025-09-05T08:47:23.868+00:00",
        "jobUrl": "https://jobs.ashbyhq.com/camunda/89fb70ec",
        "descriptionPlain": "Lead a team",
        "isRemote": True,
        "isListed": True,
        "_company": "Camunda",
    }, "89fb70ec", "https://jobs.ashbyhq.com/camunda/89fb70ec"), 1)
    assert job["company_name"] == "Camunda"
    assert job["remote"] == "remote"
    assert job["employment_type"] == "FullTime"


def test_workable_mapping_builds_location_from_parts():
    job = normalize("workable", wrap({
        "title": "Platform Lead",
        "shortcode": "70510AB5E1",
        "url": "https://apply.workable.com/j/70510AB5E1",
        "published_on": "2025-12-17",
        "employment_type": "Full-time",
        "telecommuting": True,
        "city": "Munich",
        "country": "Germany",
        "description": "<p>Own the platform</p>",
        "requirements": "<p>Ten years</p>",
        "_company": "Usercentrics",
    }, "70510AB5E1", "https://apply.workable.com/j/70510AB5E1"), 1)
    assert job["company_name"] == "Usercentrics"
    assert job["country"] == "DE"
    assert job["city"] == "Munich"
    assert "Own the platform" in job["description"]
    assert "Ten years" in job["description"]


def test_every_source_produces_the_same_job_shape():
    keys = None
    samples = [
        ("remotive", {"id": 1, "title": "T", "company_name": "C",
                      "candidate_required_location": "Europe", "description": "d",
                      "publication_date": "2026-08-01T00:00:00", "url": "https://a.test/1"}),
        ("remoteok", {"id": "2", "position": "T", "company": "C", "location": "Europe",
                      "description": "d", "url": "https://a.test/2"}),
        ("wwr", {"title": "C: T", "region": "Europe", "description": "d",
                 "link": "https://a.test/3"}),
        ("greenhouse", {"id": 4, "title": "T", "location": {"name": "Berlin"},
                        "absolute_url": "https://a.test/4", "content": "d",
                        "_company": "C"}),
        ("lever", {"id": "5", "text": "T", "categories": {"location": "Berlin"},
                   "hostedUrl": "https://a.test/5", "descriptionPlain": "d",
                   "_company": "C"}),
        ("ashby", {"id": "6", "title": "T", "location": "Berlin",
                   "jobUrl": "https://a.test/6", "descriptionPlain": "d",
                   "_company": "C"}),
        ("workable", {"title": "T", "shortcode": "7", "url": "https://a.test/7",
                      "city": "Berlin", "country": "Germany", "description": "d",
                      "_company": "C"}),
    ]
    for name, payload in samples:
        job = normalize(name, wrap(payload, "x", payload.get("url") or "https://a.test/x"), 1)
        if keys is None:
            keys = set(job)
        assert set(job) == keys, name


def test_wwr_feed_parsing():
    body = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<item><title>Co: Role</title><region>Europe</region>"
        "<link>https://weworkremotely.com/x</link></item>"
        "</channel></rss>"
    )
    rows = parse_feed(body)
    assert rows == [{"title": "Co: Role", "region": "Europe",
                     "link": "https://weworkremotely.com/x"}]


def test_watchlist_loads_and_groups(tmp_path):
    path = tmp_path / "w.yaml"
    path.write_text(
        "companies:\n"
        "  - {name: N26, ats: greenhouse, token: n26}\n"
        "  - {name: Aircall, ats: lever, token: aircall}\n"
        "  - {name: Skipped, ats: greenhouse, token: skip, enabled: false}\n"
        "  - {name: Bad, ats: nosuchats, token: x}\n"
        "  - {name: Dupe, ats: greenhouse, token: n26}\n",
        encoding="utf-8",
    )
    companies = watchlist.load(str(path))
    assert [c["name"] for c in companies] == ["N26", "Aircall"]
    assert sorted(watchlist.by_kind(companies)) == ["greenhouse", "lever"]


def test_watchlist_missing_file_is_empty(tmp_path):
    assert watchlist.load(str(tmp_path / "nope.yaml")) == []
