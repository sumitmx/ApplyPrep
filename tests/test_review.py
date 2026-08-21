import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.documents import review

JOB = {
    "title": "Automation Architect", "company": "Zalando SE",
    "city": "Berlin", "country": "DE",
    "description": "We need strong RPA and Python skills.",
}


def test_review_cv_filters_blank_items(monkeypatch):
    monkeypatch.setattr(review.agent, "run_json", lambda *a, **k: {
        "strengths": ["Deep RPA background", "  ", "", "Strong Python delivery"],
        "improvements": ["No cloud certifications listed", ""],
        "suggestions": [
            {"topic": "UiPath Rollout",
             "text": "Add a line about leading the UiPath rollout",
             "requirement": "UiPath at scale", "why": "matches the posting"},
            {"text": "  ", "why": "blank, should be dropped"},
            {"text": "Mention Terraform experience", "why": ""},
        ],
    })
    result = review.review_cv(JOB, "Some tailored CV text")
    assert result["strengths"] == ["Deep RPA background", "Strong Python delivery"]
    assert result["improvements"] == ["No cloud certifications listed"]
    assert result["suggestions"] == [
        {"topic": "UiPath Rollout",
         "text": "Add a line about leading the UiPath rollout",
         "requirement": "UiPath at scale", "why": "matches the posting"},
        {"topic": None, "text": "Mention Terraform experience",
         "requirement": None, "why": None},
    ]


def test_review_cv_rejects_empty_cv_text():
    try:
        review.review_cv(JOB, "   ")
        assert False, "expected AgentError"
    except review.agent.AgentError:
        pass
