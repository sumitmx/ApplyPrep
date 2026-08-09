import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import dedup, service, store


def add(conn, src, job_id, title, company, city, url):
    store.upsert_job(conn, {
        "dedup_key": "key-" + str(job_id),
        "title": title,
        "company_name": company,
        "city": city,
        "country": "DE",
        "url": url,
        "description": "text",
        "posted_at": "2026-08-01T00:00:00+00:00",
        "source_ids": [src],
    })


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "dedup.db"))
    store.init(c)
    return c


def test_pass_one_matches_the_same_url_written_differently(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://www.acme.test/jobs/7")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "http://acme.test/jobs/7/?utm=x")
    groups = dedup.pass_url(dedup.rows(conn))
    assert groups == [[1, 2]]


def test_pass_two_matches_the_same_role_at_different_urls(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    assert dedup.pass_structural(dedup.rows(conn)) == [[1, 2]]


def test_pass_three_matches_reworded_titles(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Architect, Automation", "Acme", "Berlin", "https://b.test/2")
    assert dedup.pass_fuzzy(dedup.rows(conn)) == [[1, 2]]


def test_pass_three_refuses_to_merge_different_seniority(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Senior Software Engineer", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Software Engineer", "Acme", "Berlin", "https://b.test/2")
    assert dedup.pass_fuzzy(dedup.rows(conn)) == []


def test_pass_three_refuses_to_merge_across_companies(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Globex", "Berlin", "https://b.test/2")
    assert dedup.pass_fuzzy(dedup.rows(conn)) == []


def test_pass_three_refuses_to_merge_across_cities(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Munich", "https://b.test/2")
    assert dedup.pass_fuzzy(dedup.rows(conn)) == []


def test_find_combines_overlapping_groups(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://a.test/1?x=1")
    add(conn, src, 3, "Architect, Automation", "Acme", "Berlin", "https://c.test/3")
    assert dedup.find(conn)["groups"] == [[1, 2, 3]]


def test_apply_keeps_the_scored_job_and_moves_nothing_else(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    service.save_score(conn, 2, fit=80, reach=40)

    result = dedup.apply(conn, [[1, 2]])
    assert result["jobs_removed"] == 1
    assert result["removed_ids"] == [1]
    left = [r["id"] for r in conn.execute("SELECT id FROM job")]
    assert left == [2]
    assert conn.execute("SELECT COUNT(*) AS n FROM score").fetchone()["n"] == 1


def test_apply_merges_source_ids(conn):
    one = store.source_id(conn, "arbeitnow", "aggregator")
    two = store.source_id(conn, "remotive", "aggregator")
    add(conn, one, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, two, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    dedup.apply(conn, [[1, 2]])
    row = conn.execute("SELECT source_ids FROM job").fetchone()
    assert str(one) in row["source_ids"] and str(two) in row["source_ids"]


def test_apply_moves_documents_to_the_survivor(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    store.save_document(conn, 2, "cv", body="draft")
    dedup.apply(conn, [[1, 2]])
    row = conn.execute("SELECT job_id FROM document").fetchone()
    assert row["job_id"] == 2


def test_apply_refuses_when_both_sides_have_applications(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    conn.execute("INSERT INTO application (job_id, status) VALUES (1, 'applied')")
    conn.execute("INSERT INTO application (job_id, status) VALUES (2, 'applied')")
    conn.commit()
    result = dedup.apply(conn, [[1, 2]])
    assert result["groups_merged"] == 0
    assert result["blocked"][0]["group"] == [1, 2]
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 2


def test_describe_reports_what_would_be_kept(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Automation Architect", "Acme", "Berlin", "https://b.test/2")
    described = dedup.describe(conn, [[1, 2]])
    assert described[0]["keep"] == 1
    assert len(described[0]["members"]) == 2


def test_no_duplicates_means_no_groups(conn):
    src = store.source_id(conn, "arbeitnow", "aggregator")
    add(conn, src, 1, "Automation Architect", "Acme", "Berlin", "https://a.test/1")
    add(conn, src, 2, "Data Engineer", "Globex", "Munich", "https://b.test/2")
    assert dedup.find(conn)["groups"] == []
