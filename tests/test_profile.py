import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.profile import match_skills

MASTER = {
    "skills": {
        "core": [{"name": "RAG"}, {"name": "Python"}],
        "working": [{"name": "GCP"}],
        "familiar": [],
    }
}


def test_match_skills_does_not_match_inside_a_word():
    text = "We use lots of GPU compute, storage and networking technology."
    matched = match_skills(MASTER, text)
    assert matched["core"] == []


def test_match_skills_matches_a_standalone_word():
    text = "Building a RAG pipeline with Python."
    matched = match_skills(MASTER, text)
    names = {s["name"] for s in matched["core"]}
    assert names == {"RAG", "Python"}


def test_match_skills_handles_empty_text():
    assert match_skills(MASTER, "") == {"core": [], "working": [], "familiar": []}


def test_match_skills_handles_no_master():
    assert match_skills(None, "anything") == {"core": [], "working": [], "familiar": []}
