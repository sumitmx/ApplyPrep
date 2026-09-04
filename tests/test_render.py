import sys
import zipfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import service, store
from jobagent.documents import guard, render, tailor

ROOT = Path(__file__).resolve().parents[1]
MASTER = yaml.safe_load((ROOT / "master.example.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def conn(tmp_path):
    c = store.connect(str(tmp_path / "r.db"))
    store.init(c)
    src = store.source_id(c, "arbeitnow", "aggregator")
    store.upsert_job(c, {
        "dedup_key": "k1",
        "title": "Automation Architect",
        "company_name": "Zalando SE",
        "country": "DE",
        "url": "https://example.test/1",
        "description": "Python and Terraform.",
        "posted_at": "2026-08-07T00:00:00+00:00",
        "source_ids": [src],
    })
    return c


def _draft():
    return guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.meridian.b1", "action": "rewrote", "text": "Reworded bullet"},
        {"id": "exp.orion.b1", "action": "dropped"},
    ], MASTER)


def test_cv_docx_is_a_real_word_file(tmp_path):
    content = tailor.build_cv_content(_draft(), MASTER)
    path = render.cv_docx(content, tmp_path / "cv.docx")
    assert path.exists() and path.stat().st_size > 5000
    with zipfile.ZipFile(path) as z:
        assert "word/document.xml" in z.namelist()
        body = z.read("word/document.xml").decode("utf-8")
    assert "Alex Morgan" in body
    assert "PROFESSIONAL EXPERIENCE" in body
    assert "Reworded bullet" in body
    assert "proof of concept" not in body


def test_cv_docx_has_no_tables_or_text_boxes(tmp_path):
    content = tailor.build_cv_content(_draft(), MASTER)
    path = render.cv_docx(content, tmp_path / "cv.docx")
    with zipfile.ZipFile(path) as z:
        body = z.read("word/document.xml").decode("utf-8")
    assert "<w:tbl>" not in body
    assert "<w:txbxContent>" not in body


def test_cv_docx_uses_the_chosen_accent_color(tmp_path):
    content = tailor.build_cv_content(_draft(), MASTER)
    navy_path = render.cv_docx(content, tmp_path / "navy.docx", accent="navy")
    teal_path = render.cv_docx(content, tmp_path / "teal.docx", accent="teal")
    with zipfile.ZipFile(navy_path) as z:
        navy_body = z.read("word/document.xml").decode("utf-8")
    with zipfile.ZipFile(teal_path) as z:
        teal_body = z.read("word/document.xml").decode("utf-8")
    assert "1F3864" in navy_body
    assert "1F6B66" in teal_body
    assert "1F6B66" not in navy_body


def test_letter_docx_has_greeting_and_sign_off(tmp_path):
    path = render.letter_docx("First para.\n\nSecond para.",
                              MASTER["identity"], tmp_path / "letter.docx")
    with zipfile.ZipFile(path) as z:
        body = z.read("word/document.xml").decode("utf-8")
    assert "Dear hiring team," in body
    assert "Warm regards," in body
    assert "Second para." in body


def test_save_dialog_opens_outside_the_project():
    """A tailored CV is not kept, so it must not default into a project folder."""
    suggested = render.suggested_dir()
    assert suggested.is_dir()
    assert Path("documents").resolve() not in suggested.resolve().parents
    assert suggested.resolve() != Path("documents").resolve()


def test_saving_writes_the_file_and_keeps_no_copy(conn, tmp_path):
    """The whole point: once the CV has gone out, the app keeps nothing."""
    store.save_document(conn, 1, "cv",
                        payload={"structured": tailor.build_cv_content(_draft(), MASTER)})
    assert service.stored_document(conn, 1, "cv")["has_file"] is False

    result = service.accept_document(conn, 1, "cv", MASTER, str(tmp_path / "docs"))
    assert result["accepted"] is True

    written = Path(result["path"])
    assert written.exists(), "the file the candidate asked for must still be written"
    assert service.stored_document(conn, 1, "cv") is None, "no draft may survive the save"


def test_saving_still_records_that_the_job_was_applied_to(conn, tmp_path):
    """Dropping the draft must not lose the fact that you applied."""
    store.save_document(conn, 1, "cv",
                        payload={"structured": tailor.build_cv_content(_draft(), MASTER)})
    service.accept_document(conn, 1, "cv", MASTER, str(tmp_path / "docs"))

    row = conn.execute("SELECT status FROM application WHERE job_id = 1").fetchone()
    assert row is not None


def test_discard_removes_an_unsaved_draft(conn):
    store.save_document(conn, 1, "cv",
                        payload={"structured": tailor.build_cv_content(_draft(), MASTER)})
    service.discard_document(conn, 1, "cv")
    assert service.stored_document(conn, 1, "cv") is None


def test_nothing_is_written_to_disk_before_save(conn, tmp_path):
    store.save_document(conn, 1, "cv", payload={"rendered": "PROFESSIONAL SUMMARY\nx"})
    assert not list((tmp_path).glob("**/*.docx"))


def test_discard_on_nothing_returns_none(conn):
    assert service.discard_document(conn, 1, "cv") is None
    assert service.accept_document(conn, 1, "cv", MASTER) is None


def _fake_tailor_response():
    return {
        "changes": [
            {"id": "exp.northstar.b1", "action": "kept"},
            {"id": "exp.meridian.b1", "action": "rewrote", "text": "Reworded bullet"},
        ],
        "note": "Leaned into automation delivery.",
    }


def test_generate_cv_clears_a_stale_stored_review(conn, monkeypatch):
    monkeypatch.setattr(tailor.agent, "run_json", lambda *a, **k: _fake_tailor_response())
    service.generate_cv(conn, 1, MASTER)
    store.save_document(conn, 1, "review",
                        payload={"strengths": ["x"], "improvements": [], "suggestions": []})
    assert service.stored_review(conn, 1) is not None

    service.generate_cv(conn, 1, MASTER)
    assert service.stored_review(conn, 1) is None


def test_add_cv_highlight_appends_into_one_section_across_repeated_calls(conn, monkeypatch):
    monkeypatch.setattr(tailor.agent, "run_json", lambda *a, **k: _fake_tailor_response())
    service.generate_cv(conn, 1, MASTER)

    first = service.add_cv_highlight(conn, 1, MASTER, "Led a cross-team automation initiative")
    sections = [s for s in first["structured"]["sections"] if s["kind"] == "highlights"]
    assert len(sections) == 1
    assert sections[0]["heading"] == "ADDITIONAL HIGHLIGHTS"
    assert sections[0]["items"] == ["Led a cross-team automation initiative"]
    assert "Led a cross-team automation initiative" in first["rendered"]
    assert first["ats_score"] is not None

    second = service.add_cv_highlight(conn, 1, MASTER, "Mentored two junior engineers")
    sections = [s for s in second["structured"]["sections"] if s["kind"] == "highlights"]
    assert len(sections) == 1
    assert sections[0]["items"] == [
        "Led a cross-team automation initiative", "Mentored two junior engineers",
    ]

    stored = service.stored_document(conn, 1, "cv")
    assert stored["payload"]["structured"] == second["structured"]


def test_add_cv_highlight_rejects_blank_text(conn, monkeypatch):
    monkeypatch.setattr(tailor.agent, "run_json", lambda *a, **k: _fake_tailor_response())
    service.generate_cv(conn, 1, MASTER)
    with pytest.raises(ValueError):
        service.add_cv_highlight(conn, 1, MASTER, "   ")


def test_add_cv_highlight_raises_on_legacy_payload_without_structured(conn):
    store.save_document(conn, 1, "cv", payload={"rendered": "Alex Morgan\nStuff"})
    with pytest.raises(service.ExportUnavailable):
        service.add_cv_highlight(conn, 1, MASTER, "Some text")
