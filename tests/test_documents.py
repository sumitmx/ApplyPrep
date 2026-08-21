import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import profile
from jobagent.documents import coverage, guard, lint, tailor

MASTER = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "master.example.yaml").read_text(encoding="utf-8")
)


def test_master_yaml_parses_and_has_bullets():
    assert MASTER["identity"]["name"] == "Alex Morgan"
    bullets = guard.known_bullets(MASTER)
    assert len(bullets) >= 15
    assert "exp.northstar.b1" in bullets
    assert "proj.rag" in bullets


def test_every_bullet_id_is_unique():
    ids = []
    for role in MASTER["experience"]:
        ids += [b["id"] for b in role["bullets"]]
    ids += [p["id"] for p in MASTER["projects"]]
    assert len(ids) == len(set(ids))


def test_skill_tiers_load():
    tiers = profile.skill_tiers(MASTER)
    assert any(s["name"] == "UiPath" for s in tiers["core"])
    assert any(s["name"] == "React" for s in tiers["familiar"])
    assert all(s.get("context") for s in tiers["core"])


def test_guard_accepts_real_bullet_ids():
    clean = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.meridian.b1", "action": "rewrote", "text": "Reworded version"},
    ], MASTER)
    assert len(clean) == 2
    assert clean[1]["was"].startswith("Designed and shipped")
    assert clean[1]["text"] == "Reworded version"


def test_guard_rejects_an_invented_bullet():
    with pytest.raises(guard.FabricationError) as exc:
        guard.check([
            {"id": "exp.northstar.b1", "action": "kept"},
            {"id": "exp.google.b9", "action": "pulled", "text": "Invented work"},
        ], MASTER)
    assert "exp.google.b9" in str(exc.value)


def test_guard_rejects_a_missing_id():
    with pytest.raises(guard.FabricationError):
        guard.check([{"action": "kept", "text": "no id here"}], MASTER)


def test_guard_rejects_an_unknown_action():
    with pytest.raises(guard.FabricationError) as exc:
        guard.check([{"id": "exp.orion.b1", "action": "embellished"}], MASTER)
    assert "embellished" in str(exc.value)


def test_guard_keeps_original_text_when_none_supplied():
    clean = guard.check([{"id": "exp.orion.b1", "action": "kept"}], MASTER)
    assert "Built the bank's first automation capability" in clean[0]["text"]


def test_dropped_bullets_are_not_in_the_cv_text():
    clean = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.orion.b1", "action": "dropped"},
    ], MASTER)
    text = guard.selected_text(clean)
    assert "AI alerting system" in text
    assert "Orion" not in text and "proof of concept" not in text


def test_coverage_splits_into_three_buckets():
    job = "We need strong UiPath and Terraform skills, plus Kubernetes and Rust."
    cv = "Automation on UiPath across banking."
    result = coverage.analyse(job, cv, MASTER)
    covered = [c["term"] for c in result["covered"]]
    fixable = [c["term"] for c in result["fixable"]]
    assert "uipath" in covered
    assert "terraform" in fixable
    assert result["counts"]["covered"] == len(covered)


def test_coverage_never_returns_a_percentage():
    result = coverage.analyse("Python and Go", "Python", MASTER)
    assert set(result["counts"]) == {"covered", "fixable", "real_gap"}
    assert "score" not in result and "percent" not in result


def test_ats_score_is_covered_share_of_wanted_terms():
    assert tailor._ats_score({"covered": 3, "fixable": 1, "real_gap": 0}) == 75


def test_ats_score_rounds_to_nearest_percent():
    assert tailor._ats_score({"covered": 1, "fixable": 1, "real_gap": 1}) == 33


def test_ats_score_is_none_when_nothing_is_wanted():
    assert tailor._ats_score({"covered": 0, "fixable": 0, "real_gap": 0}) is None


def test_aliases_stop_false_gaps():
    job = "You will work with GCP and Kubernetes every day."
    result = coverage.analyse(job, "Cloud delivery work.", MASTER)
    gaps = [c["term"] for c in result["real_gap"]]
    assert "gcp" not in gaps
    assert "kubernetes" in gaps


def test_bullet_skill_tags_count_as_owned():
    result = coverage.analyse("We build with LLM and RAG systems.", "", MASTER)
    gaps = [c["term"] for c in result["real_gap"]]
    assert "llm" not in gaps
    owned = coverage.skill_names(MASTER)
    assert "llm" in owned and "vertex ai" in owned


def test_a_skill_on_the_cv_is_covered_not_fixable():
    result = coverage.analyse("Python required.", "Built pipelines in Python.", MASTER)
    assert "python" in [c["term"] for c in result["covered"]]
    assert "python" not in [c["term"] for c in result["fixable"]]


def test_a_skill_owned_but_absent_from_the_cv_is_fixable():
    result = coverage.analyse("Terraform required.", "No mention here.", MASTER)
    assert "terraform" in [c["term"] for c in result["fixable"]]


def test_render_cv_has_headings_and_dates():
    changes = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.orion.b1", "action": "dropped"},
    ], MASTER)
    text = tailor.render_cv(changes, MASTER)
    assert "PROFESSIONAL EXPERIENCE" in text
    assert "Oct 2025 - Present" in text
    assert "AI alerting system" in text
    assert "proof of concept" not in text


def test_flatten_cv_of_build_cv_content_matches_render_cv():
    changes = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.orion.b1", "action": "dropped"},
    ], MASTER)
    content = tailor.build_cv_content(changes, MASTER)
    assert tailor.flatten_cv(content) == tailor.render_cv(changes, MASTER)


def test_build_cv_content_has_expected_section_order_and_identity():
    changes = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
    ], MASTER)
    content = tailor.build_cv_content(changes, MASTER)
    assert content["identity"]["name"] == "Alex Morgan"
    kinds = [s["kind"] for s in content["sections"]]
    assert kinds[0] == "skills"
    assert kinds[1] == "experience"
    assert "education" in kinds
    experience = next(s for s in content["sections"] if s["kind"] == "experience")
    role = experience["roles"][0]
    assert role["bullets"] == ["Own the architecture of an AI alerting system on "
                               "Google Cloud that tracks SLA adherence in a "
                               "ticket-management system and sends case owners "
                               "real-time alerts with AI recommendations"]


def test_palette_entries_have_a_label_and_a_valid_hex():
    import re as _re
    from jobagent.documents import palette
    assert palette.DEFAULT_ACCENT in palette.ACCENTS
    for entry in palette.ACCENTS.values():
        assert entry["label"]
        assert _re.match(r"^#[0-9A-Fa-f]{6}$", entry["hex"])


def test_palette_resolve_falls_back_to_default_for_unknown_key():
    from jobagent.documents import palette
    resolved = palette.resolve("not-a-real-color")
    default = palette.ACCENTS[palette.DEFAULT_ACCENT]
    assert {k: resolved[k] for k in default} == default
    assert resolved["ink"], "resolve should also hand back a readable ink"


def test_every_accent_has_readable_type_on_its_own_band():
    """A light accent with white type would be unreadable. ink_for picks the
    contrast winner, so no accent may fall below the WCAG AA threshold."""
    from jobagent.documents import palette
    for key, entry in palette.ACCENTS.items():
        ratio = palette.contrast(entry["hex"], palette.ink_for(entry["hex"]))
        assert ratio >= 4.5, key + " only reaches " + str(round(ratio, 2)) + ":1"


def test_light_accents_are_darkened_before_being_used_as_text():
    """The accent doubles as type on white paper. Light ones have to come down
    to stay legible; deep ones should be left exactly as they are."""
    from jobagent.documents import palette
    for key, entry in palette.ACCENTS.items():
        on_paper = palette.on_paper(entry["hex"])
        ratio = palette.contrast(on_paper, "#FFFFFF")
        assert ratio >= 4.5, key + " as text is only " + str(round(ratio, 2)) + ":1"
        if entry["tone"] == "deep":
            assert on_paper == entry["hex"], key + " should not have been altered"


def test_lint_returns_pass_fail_not_a_score():
    result = lint.check("PROFESSIONAL EXPERIENCE\nBuilt things Mar 2021 to Feb 2022.")
    assert result["passed"] + result["failed"] == len(result["checks"])
    assert all(isinstance(c["pass"], bool) for c in result["checks"])
    assert "score" not in result


def test_lint_flags_unexplained_acronyms():
    result = lint.check("Delivered RPA work across banking. Experience since 2014.")
    flagged = [c for c in result["checks"] if c["check"].startswith("Acronyms")]
    assert flagged[0]["pass"] is False
    assert "RPA" in flagged[0]["detail"]
