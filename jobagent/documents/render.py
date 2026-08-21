import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from . import palette

GRAY = RGBColor(0x59, 0x59, 0x59)
BLACK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _accent_rgb(accent):
    hex_value = palette.resolve(accent)["hex"].lstrip("#")
    return RGBColor(int(hex_value[0:2], 16), int(hex_value[2:4], 16), int(hex_value[4:6], 16))


def _shade(paragraph, hex_value):
    """Fill a paragraph's background - single-column shading, not a table, so
    it stays invisible to ATS text extraction while giving a colored band."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_value)
    paragraph._p.get_or_add_pPr().append(shd)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "job"


def folder(base, job_id, company):
    path = Path(base) / (str(job_id).rjust(3, "0") + "-" + slug(company))
    path.mkdir(parents=True, exist_ok=True)
    return path


def ask_save_path(default_dir, default_filename):
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        chosen = filedialog.asksaveasfilename(
            parent=root,
            title="Save Word file",
            initialdir=str(default_dir),
            initialfile=default_filename,
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


def _base_document():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.paragraph_format.space_after = Pt(4)
    return doc


def _run(para, text, bold=False, color=BLACK, size=9.5):
    run = para.add_run(text)
    run.bold = bold
    run.font.color.rgb = color
    run.font.size = Pt(size)
    return run


def _heading(doc, text, accent_hex):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(10)
    para.paragraph_format.space_after = Pt(4)
    _shade(para, accent_hex)
    _run(para, text, bold=True, color=WHITE, size=12)
    return para


def cv_docx(content, path, accent=palette.DEFAULT_ACCENT):
    doc = _base_document()
    accent_rgb = _accent_rgb(accent)
    accent_hex = palette.resolve(accent)["hex"].lstrip("#")
    identity = content.get("identity") or {}

    name_para = doc.add_paragraph()
    name_para.paragraph_format.space_before = Pt(6)
    name_para.paragraph_format.space_after = Pt(2)
    _shade(name_para, accent_hex)
    _run(name_para, identity.get("name", ""), bold=True, color=WHITE, size=24)

    headline = identity.get("headline")
    if headline:
        headline_para = doc.add_paragraph()
        headline_para.paragraph_format.space_after = Pt(2)
        _shade(headline_para, accent_hex)
        _run(headline_para, headline, bold=True, color=WHITE, size=10.5)

    contact = " | ".join(
        str(v) for v in [
            identity.get("location"), identity.get("phone"),
            identity.get("email"), identity.get("linkedin"),
        ] if v
    )
    if contact:
        contact_para = doc.add_paragraph()
        contact_para.paragraph_format.space_after = Pt(6)
        _shade(contact_para, accent_hex)
        _run(contact_para, contact, bold=False, color=WHITE, size=9)

    summary = content.get("summary")
    if summary:
        _heading(doc, "PROFESSIONAL SUMMARY", accent_hex)
        para = doc.add_paragraph()
        _run(para, summary, bold=False, color=BLACK, size=9.5)

    for section in content.get("sections") or []:
        kind = section["kind"]
        _heading(doc, section["heading"], accent_hex)

        if kind == "skills":
            for tier in section["tiers"]:
                para = doc.add_paragraph()
                _run(para, tier["label"] + ": ", bold=True, color=accent_rgb, size=9.5)
                _run(para, ", ".join(tier["items"]), bold=False, color=BLACK, size=9.5)

        elif kind == "experience":
            for role in section["roles"]:
                para = doc.add_paragraph()
                _run(para, role["title"], bold=True, color=BLACK, size=11)
                _run(para, ", " + role["company"], bold=False, color=accent_rgb, size=11)
                if role.get("client"):
                    client_para = doc.add_paragraph()
                    _run(client_para, "Client: " + role["client"],
                         bold=False, color=accent_rgb, size=9.5)
                loc_para = doc.add_paragraph()
                location = role.get("location") or ""
                _run(loc_para, (location + "    " if location else "") + role["period"],
                     bold=False, color=GRAY, size=9)
                for bullet in role["bullets"]:
                    para = doc.add_paragraph(style="List Bullet")
                    _run(para, bullet, bold=False, color=BLACK, size=9.5)

        elif kind == "projects":
            for item in section["items"]:
                para = doc.add_paragraph(style="List Bullet")
                _run(para, item["name"] + ":", bold=True, color=BLACK, size=9.5)
                _run(para, " " + item["text"], bold=False, color=BLACK, size=9.5)

        elif kind == "education":
            for item in section["items"]:
                para = doc.add_paragraph()
                _run(para, item["degree"], bold=True, color=BLACK, size=9.5)
                _run(para, "  -  " + item["school"] + " (" + item["years"] + ")",
                     bold=False, color=BLACK, size=9.5)

        elif kind == "certifications":
            for item in section["items"]:
                para = doc.add_paragraph(style="List Bullet")
                _run(para, item, bold=False, color=BLACK, size=9.5)

        elif kind == "languages":
            for lang in section["items"]:
                text = (
                    (lang["name"] + " (" + lang["level"] + ")")
                    if lang.get("level") else lang["name"]
                )
                para = doc.add_paragraph(style="List Bullet")
                _run(para, text, bold=False, color=BLACK, size=9.5)

        elif kind == "highlights":
            for item in section["items"]:
                para = doc.add_paragraph(style="List Bullet")
                _run(para, item, bold=False, color=BLACK, size=9.5)

    doc.save(path)
    return path


def letter_docx(body, identity, path):
    doc = _base_document()

    name = doc.add_paragraph()
    run = name.add_run((identity or {}).get("name", ""))
    run.bold = True
    run.font.size = Pt(14)

    contact = " | ".join(
        str(v) for v in [
            (identity or {}).get("location"),
            (identity or {}).get("email"),
            (identity or {}).get("phone"),
        ] if v
    )
    if contact:
        doc.add_paragraph(contact)

    doc.add_paragraph("")
    doc.add_paragraph("Dear hiring team,")
    doc.add_paragraph("")

    for para in re.split(r"\n\s*\n", (body or "").strip()):
        cleaned = " ".join(para.split())
        if cleaned:
            doc.add_paragraph(cleaned)

    doc.add_paragraph("")
    doc.add_paragraph("Warm regards,")
    doc.add_paragraph((identity or {}).get("name", ""))

    doc.save(str(path))
    return path
