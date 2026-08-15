import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.profile import append_skills, existing_names, load_master, match_skills

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


def test_existing_names_covers_all_tiers():
    assert existing_names(MASTER) == {"rag", "python", "gcp"}


def test_append_skills_preserves_untouched_formatting(tmp_path):
    path = tmp_path / "master.yaml"
    path.write_text(
        "identity:\n"
        "  name: Test Person\n"
        "  phone: \"+1 555 0100\"\n"
        "summary: >-\n"
        "  A folded block of text\n"
        "  that spans lines.\n"
        "skills:\n"
        "  core:\n"
        "  - name: RAG\n"
        "  working:\n"
        "  - name: GCP\n"
        "  familiar: []\n",
        encoding="utf-8",
    )
    append_skills(str(path), {
        "core": [{"name": "Kubernetes", "context": "2 years"}],
        "familiar": [{"name": "Rust"}],
    })
    text = path.read_text(encoding="utf-8")
    # untouched lines come back byte-identical
    assert 'phone: "+1 555 0100"' in text
    assert "summary: >-" in text
    reloaded = load_master(str(path))
    assert {s["name"] for s in reloaded["skills"]["core"]} == {"RAG", "Kubernetes"}
    assert reloaded["skills"]["working"][0]["name"] == "GCP"
    assert reloaded["skills"]["familiar"][0]["name"] == "Rust"


def test_append_skills_creates_missing_tier_and_file(tmp_path):
    path = tmp_path / "master.yaml"
    append_skills(str(path), {"working": [{"name": "Docker"}]})
    reloaded = load_master(str(path))
    assert reloaded["skills"]["working"][0]["name"] == "Docker"
