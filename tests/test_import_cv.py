"""The CV upload is the source of truth for master.yaml.

The rules worth protecting: bullets are never invented, ids survive a
re-import, skills stay matchable against job adverts, and a bad extraction
never replaces a good profile.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import profile
from jobagent.documents import guard, import_cv

CV_TEXT = """
Sam Rivers
Berlin, Germany | sam@example.com | +49 30 000000

Principal Engineer with 15 years building automation.

EXPERIENCE
Northwind GmbH - Principal Engineer - 2022-01 to present
- Designed the alerting platform on Google Cloud that tracks SLA adherence
- Ran delivery across a team of nine from architecture through rollout

PROJECTS
Knowledge Assistant
- Retrieval chatbot over a vector database
- Streamlit front end for natural language querying

SKILLS
Python, BigQuery, Looker, Terraform
"""

EXTRACTED = {
    "identity": {"name": "Sam Rivers", "location": "Berlin, Germany",
                 "email": "sam@example.com"},
    "summary": "Principal Engineer with 15 years building automation.",
    "experience": [{
        "company": "Northwind GmbH", "title": "Principal Engineer",
        "start": "2022-01", "end": "present",
        "bullets": [
            {"text": "Designed the alerting platform on Google Cloud that tracks SLA adherence",
             "skills": ["gcp"]},
            {"text": "Ran delivery across a team of nine from architecture through rollout"},
        ],
    }],
    "projects": [
        {"name": "Knowledge Assistant", "text": "Retrieval chatbot over a vector database"},
        {"name": "Knowledge Assistant", "text": "Streamlit front end for natural language querying"},
    ],
    "skills": {"core": [{"name": "Python", "context": "15 yr"}],
               "working": [{"name": "BigQuery / Looker", "context": "reporting"}],
               "familiar": []},
    "certifications": ["ITIL"],
    "education": [], "languages": [],
}


def _build(extracted=None, previous=None):
    return import_cv.build(extracted or EXTRACTED, previous or {}, CV_TEXT)


# ── the guarantee that matters most ────────────────────────────────────────

def test_a_bullet_the_cv_does_not_contain_is_dropped():
    """Invented text must never reach master.yaml - guard.py depends on it."""
    invented = {
        **EXTRACTED,
        "experience": [{
            "company": "Northwind GmbH",
            "bullets": [
                {"text": "Designed the alerting platform on Google Cloud that tracks SLA adherence"},
                {"text": "Grew revenue by 40 percent and led a department of two hundred"},
            ],
        }],
    }
    master, summary = _build(invented)
    texts = [b["text"] for r in master["experience"] for b in r["bullets"]]

    assert len(texts) == 1
    assert not any("revenue" in t for t in texts)
    assert summary["bullets_not_in_cv"] == 1


def test_bullets_are_copied_word_for_word():
    master, _ = _build()
    assert master["experience"][0]["bullets"][0]["text"] in CV_TEXT


# ── ids survive, so tailoring history is not orphaned ──────────────────────

def test_reimporting_keeps_the_ids_a_bullet_already_had():
    first, _ = _build()
    second, summary = _build(previous=first)

    before = [b["id"] for r in first["experience"] for b in r["bullets"]]
    after = [b["id"] for r in second["experience"] for b in r["bullets"]]
    assert before == after
    assert summary["bullet_ids_kept"] == len(before) + len(first["projects"])


def test_every_bullet_id_is_unique():
    master, _ = _build()
    ids = [b["id"] for r in master["experience"] for b in r["bullets"]]
    ids += [p["id"] for p in master["projects"]]
    assert len(ids) == len(set(ids))


def test_the_guard_can_read_what_was_written():
    master, _ = _build()
    assert len(guard.known_bullets(master)) == 3


# ── skills have to stay matchable ──────────────────────────────────────────

@pytest.mark.parametrize("grouped,expected", [
    ("BigQuery / Looker", ["BigQuery", "Looker"]),
    ("CI/CD (Jenkins, GitLab)", ["CI/CD", "Jenkins", "GitLab"]),
    ("Python", ["Python"]),
    ("Node.js", ["Node.js"]),
    ("Team & Programme Leadership", ["Team & Programme Leadership"]),
    ("Research and Development", ["Research and Development"]),
])
def test_grouped_skill_names_are_split_but_real_names_are_not(grouped, expected):
    assert import_cv.split_skill_name(grouped) == expected


def test_split_skills_actually_match_a_job_advert():
    """A grouped name matches nothing, which would silently break the gate."""
    master, _ = _build()
    advert = "we use bigquery for analytics and looker for dashboards"
    names = [s["name"] for tier in master["skills"].values() for s in tier]

    assert "BigQuery" in names and "Looker" in names
    matched = [n for n in names
               if profile._skill_pattern(n) and profile._skill_pattern(n).search(advert)]
    assert sorted(matched) == ["BigQuery", "Looker"]


# ── the CV is the source of truth ──────────────────────────────────────────

def test_skills_the_new_cv_dropped_are_removed():
    previous = {"skills": {"core": [{"name": "Fortran"}], "working": [], "familiar": []}}
    master, summary = _build(previous=previous)
    names = [s["name"] for tier in master["skills"].values() for s in tier]

    assert "Fortran" not in names
    assert "Fortran" in summary["skills_removed"]


def test_one_project_stays_one_project():
    """Models emit a project's bullets as separate projects; they get merged."""
    master, _ = _build()
    assert len(master["projects"]) == 1
    assert "vector database" in master["projects"][0]["text"]
    assert "Streamlit" in master["projects"][0]["text"]


def test_job_market_keywords_survive_a_reimport():
    previous = {"pending_keywords": ["kubernetes"]}
    master, _ = _build(previous=previous)
    assert master["pending_keywords"] == ["kubernetes"]


# ── a bad extraction must not replace a good profile ───────────────────────

@pytest.mark.parametrize("broken,expected", [
    ({"experience": []}, "experience"),
    ({"identity": {}}, "name"),
])
def test_validation_rejects_an_extraction_that_would_break_tailoring(broken, expected):
    master, _ = _build({**EXTRACTED, **broken})
    problems = import_cv.validate(master)
    assert problems
    assert any(expected in problem for problem in problems)


def test_a_good_extraction_validates():
    master, _ = _build()
    assert import_cv.validate(master) == []


def test_empty_cv_text_is_refused():
    with pytest.raises(ValueError):
        import_cv.extract("   ")


# ── writing ────────────────────────────────────────────────────────────────

def test_writing_backs_up_what_it_replaces(tmp_path):
    path = tmp_path / "master.yaml"
    path.write_text("summary: the old one\n", encoding="utf-8")

    master, _ = _build()
    backup = profile.write_master(str(path), master)

    assert backup and backup.exists()
    assert "the old one" in backup.read_text(encoding="utf-8")
    assert profile.load_master(str(path))["identity"]["name"] == "Sam Rivers"


def test_the_written_file_reloads_as_the_same_data(tmp_path):
    path = tmp_path / "master.yaml"
    master, _ = _build()
    profile.write_master(str(path), master)

    reloaded = profile.load_master(str(path))
    assert reloaded["experience"] == master["experience"]
    assert reloaded["skills"] == master["skills"]
