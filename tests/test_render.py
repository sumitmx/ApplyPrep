import sys
import zipfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent import service, store
from jobagent.documents import guard, render, tailor

ROOT = Path(__file__).resolve().parents[1]
MASTER = yaml.safe_load((ROOT / "master.yaml").read_text(encoding="utf-8"))


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


def test_folder_name_is_slugged():
    path = render.folder("documents", 47, "Zalando SE")
    assert path.name == "047-zalando-se"


def test_save_writes_a_file_and_discard_removes_it(conn, tmp_path):
    store.save_document(conn, 1, "cv",
                        payload={"structured": tailor.build_cv_content(_draft(), MASTER)})
    assert service.stored_document(conn, 1, "cv")["has_file"] is False

    result = service.accept_document(conn, 1, "cv", MASTER, str(tmp_path / "docs"))
    assert result["accepted"] is True
    written = Path(result["path"])
    assert written.exists()

    row = service.stored_document(conn, 1, "cv")
    assert row["accepted"] == 1 and row["has_file"] is True

    service.discard_document(conn, 1, "cv")
    assert written.exists() is False
    assert service.stored_document(conn, 1, "cv") is None


def test_nothing_is_written_to_disk_before_save(conn, tmp_path):
    store.save_document(conn, 1, "cv", payload={"rendered": "PROFESSIONAL SUMMARY\nx"})
    assert not list((tmp_path).glob("**/*.docx"))


def test_discard_on_nothing_returns_none(conn):
    assert service.discard_document(conn, 1, "cv") is None
    assert service.accept_document(conn, 1, "cv", MASTER) is None
