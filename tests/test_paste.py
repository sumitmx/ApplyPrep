"""Jobs pasted in by hand, for boards that cannot be scraped."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import config, pull, store

ADVERT = (
    "We are hiring a Principal Automation Architect in Berlin, Germany.\n"
    "Visa sponsorship is available for the right candidate.\n"
    "You will own the automation platform end to end."
)


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "paste.db"))
    store.init(c)
    return c


@pytest.fixture
def cfg():
    return config.load("does-not-exist.yaml")


def _paste(conn, cfg, **over):
    fields = {
        "title": "Principal Automation Architect",
        "company": "Acme GmbH",
        "description": ADVERT,
        "location": "Berlin, Germany",
    }
    fields.update(over)
    return pull.paste_job(conn, cfg, fields)


def _row(conn, job_id):
    return conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()


def test_pasting_creates_a_job(conn, cfg):
    result = _paste(conn, cfg)
    assert result["is_new"] is True
    row = _row(conn, result["job_id"])
    assert row["title"] == "Principal Automation Architect"
    assert row["company_name"] == "Acme GmbH"


def test_the_advert_text_is_mined_the_same_way_a_pulled_job_is(conn, cfg):
    """The whole point is that a pasted job is not second class - country,
    sponsorship and language all come out of the text, as they would on pull."""
    row = _row(conn, _paste(conn, cfg)["job_id"])
    assert row["country"] == "DE"
    assert row["city"] == "Berlin"
    assert row["sponsorship_status"] == "confirmed"


def test_a_pasted_job_always_passes_the_gate(conn, cfg):
    """The gate filters pulled jobs because nobody chose them. This one was
    chosen deliberately, so a title the gate would normally bin still gets in."""
    result = _paste(conn, cfg, title="Junior Sales Intern")
    row = _row(conn, result["job_id"])
    assert row["gate_status"] == "passed"


def test_reach_is_computed_so_the_job_lands_in_a_band(conn, cfg):
    job_id = _paste(conn, cfg)["job_id"]
    assert conn.execute(
        "SELECT 1 FROM job_reach WHERE job_id = ?", (job_id,)
    ).fetchone() is not None


def test_pasting_the_same_advert_twice_reopens_the_first_one(conn, cfg):
    first = _paste(conn, cfg)
    second = _paste(conn, cfg)
    assert second["job_id"] == first["job_id"]
    assert second["is_new"] is False
    assert conn.execute("SELECT COUNT(*) AS n FROM job").fetchone()["n"] == 1


def test_a_link_is_optional(conn, cfg):
    row = _row(conn, _paste(conn, cfg)["job_id"])
    assert row["url"] == "", "no link given, so nothing for the UI to render"


def test_a_link_is_used_for_dedup_when_given(conn, cfg):
    a = _paste(conn, cfg, url="https://linkedin.test/jobs/1")
    b = _paste(conn, cfg, url="https://linkedin.test/jobs/2")
    assert a["job_id"] != b["job_id"]


@pytest.mark.parametrize("missing", ["title", "company", "description"])
def test_the_three_required_fields_are_enforced(conn, cfg, missing):
    with pytest.raises(ValueError) as exc:
        _paste(conn, cfg, **{missing: "   "})
    assert missing in str(exc.value)


def test_pasted_jobs_survive_the_prune(conn, cfg):
    """They cost real effort to enter and cannot be re-pulled from anywhere,
    so ageing out would lose them for good."""
    job_id = _paste(conn, cfg, posted_at="2020-01-01T00:00:00+00:00")["job_id"]
    result = pull.prune(conn, days=7, apply=True)
    assert result["kept_because_pasted"] == 1
    assert conn.execute("SELECT 1 FROM job WHERE id = ?", (job_id,)).fetchone()
