import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import skills

MASTER = {
    "skills": {
        "core": [{"name": "Python", "context": "10 years"}],
        "working": [{"name": "Docker"}],
        "familiar": [],
    },
}


def test_extract_filters_invalid_and_dedups(monkeypatch):
    monkeypatch.setattr(skills.agent, "run_json", lambda *a, **k: {
        "skills": [
            {"name": "Kubernetes", "tier": "working", "context": "2 years"},
            {"name": "Kubernetes", "tier": "working"},
            {"name": "", "tier": "core"},
            {"name": "Rust", "tier": "not-a-tier"},
        ],
    })
    out = skills.extract("some free text", {"python", "docker"})
    assert out == [{"name": "Kubernetes", "tier": "working", "context": "2 years"}]


def test_extract_rejects_empty_text():
    try:
        skills.extract("   ", set())
        assert False, "expected AgentError"
    except skills.agent.AgentError:
        pass


def test_merge_dedups_across_all_tiers_case_insensitively():
    additions, added, skipped = skills.merge(MASTER, [
        {"name": "python", "tier": "familiar"},
        {"name": "Kubernetes", "tier": "working", "context": "2 years"},
        {"name": "Rust", "tier": "bogus"},
    ])
    assert added == [{"name": "Kubernetes", "tier": "working"}]
    assert skipped == [
        {"name": "python", "reason": "duplicate"},
        {"name": "Rust", "reason": "invalid"},
    ]
    assert additions == {
        "core": [], "working": [{"name": "Kubernetes", "context": "2 years"}], "familiar": [],
    }
    # original untouched
    assert MASTER["skills"]["working"] == [{"name": "Docker"}]


def test_find_gaps_excludes_existing_and_caps_at_eight(monkeypatch):
    monkeypatch.setattr(skills.agent, "run_json", lambda *a, **k: {
        "gaps": [{"name": "Python", "note": "already known"}]
        + [{"name": "Skill" + str(i), "note": "n"} for i in range(10)],
    })
    out = skills.find_gaps("some postings text", {"python"})
    assert len(out) == 8
    assert all(g["name"] != "Python" for g in out)


def test_find_gaps_rejects_no_postings():
    try:
        skills.find_gaps("", {"python"})
        assert False, "expected AgentError"
    except skills.agent.AgentError:
        pass
