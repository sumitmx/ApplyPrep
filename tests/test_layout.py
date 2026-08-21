"""The CV type scale is shared, so an export cannot drift from the preview."""
import sys
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.shared import Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.documents import guard, layout, pdf, render, tailor

ROOT = Path(__file__).resolve().parents[1]
MASTER = yaml.safe_load((ROOT / "master.example.yaml").read_text(encoding="utf-8"))

FONT = layout.FONT_PT
SPACE = layout.SPACE_PT


@pytest.fixture
def two_role_cv():
    """A draft spanning several employers, so spacing between them shows up."""
    changes = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.northstar.b2", "action": "kept"},
        {"id": "exp.meridian.b1", "action": "kept"},
    ], MASTER)
    return tailor.build_cv_content(changes, MASTER)


@pytest.fixture
def docx(two_role_cv, tmp_path):
    return Document(str(render.cv_docx(two_role_cv, tmp_path / "cv.docx")))


def _shaded(para):
    """Section headings sit on a colored band; body paragraphs do not."""
    return "shd" in para._p.xml


def _before(para):
    """python-docx reports an explicit zero gap as None."""
    gap = para.paragraph_format.space_before
    return 0 if gap is None else gap.pt


def _role_paragraphs(doc):
    return [
        p for p in doc.paragraphs
        if p.runs and p.runs[0].font.size == Pt(FONT["role"]) and not _shaded(p)
    ]


def test_the_scale_steps_down_from_heading_to_role_to_bullet(two_role_cv):
    """Company names have to win the eye over the detail underneath them."""
    assert FONT["heading"] > FONT["role"] > FONT["bullet"]
    assert FONT["role"] - FONT["bullet"] >= 2, "the step needs to be visible"


def test_docx_puts_air_between_employers(docx):
    roles = _role_paragraphs(docx)
    assert len(roles) >= 2, "need at least two employers to see the gap"
    assert all(_before(r) == SPACE["role_before"] for r in roles[1:])


def test_docx_does_not_indent_the_first_employer(docx):
    """The first role sits right under its heading, so it takes no extra gap."""
    assert _before(_role_paragraphs(docx)[0]) == 0


def test_docx_separates_sections(docx):
    headings = [
        p for p in docx.paragraphs
        if p.runs and p.runs[0].font.size == Pt(FONT["heading"]) and _shaded(p)
    ]
    assert len(headings) >= 2
    # The first heading butts against the contact band; the rest get air.
    assert _before(headings[0]) == 0
    assert all(_before(h) == SPACE["section_before"] for h in headings[1:])


def test_docx_bullets_render_at_the_bullet_size(docx):
    bullets = [p for p in docx.paragraphs if p.style.name == "List Bullet"]
    assert bullets, "expected bullet paragraphs"
    assert all(r.font.size == Pt(FONT["bullet"]) for p in bullets for r in p.runs)


def test_pdf_uses_the_very_same_sizes_as_word():
    """This is the mismatch that started it: the PDF role line used to render
    at body size while Word used the larger role size."""
    styles = pdf._styles("#1F3864")
    for key in ("name", "headline", "contact", "heading", "body", "bullet"):
        assert styles[key].fontSize == FONT[key], key + " drifted"
    assert styles["role"].fontSize == FONT["role"]
    assert styles["role_first"].fontSize == FONT["role"]


def test_pdf_puts_air_between_employers_too():
    styles = pdf._styles("#1F3864")
    assert styles["role"].spaceBefore == SPACE["role_before"]
    assert styles["role_first"].spaceBefore == 0
    assert styles["heading"].spaceBefore == SPACE["section_before"]


def test_the_browser_is_served_every_size_and_gap():
    """The preview reads these as CSS variables. A key missing here would
    silently fall back to a stale hardcoded value in the stylesheet."""
    css = layout.css_vars()
    for key in FONT:
        assert "--cv-fs-" + key in css
    for key in SPACE:
        assert "--cv-sp-" + key.replace("_", "-") in css
    assert all(v.endswith("px") for v in css.values())


def test_points_convert_to_css_pixels_at_the_standard_ratio():
    assert layout.css_vars()["--cv-fs-bullet"] == str(
        round(FONT["bullet"] * 96 / 72, 2)
    ) + "px"
