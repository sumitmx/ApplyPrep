import re
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

HEADINGS = {
    "PROFESSIONAL SUMMARY", "PROFESSIONAL EXPERIENCE", "KEY PROJECTS",
    "SKILLS", "EDUCATION", "CERTIFICATIONS", "LANGUAGES",
}

DARK_BLUE = RGBColor(0x1F, 0x38, 0x64)
MED_BLUE = RGBColor(0x2E, 0x54, 0x96)
GRAY = RGBColor(0x59, 0x59, 0x59)
BLACK = RGBColor(0x00, 0x00, 0x00)

_TIER_LINE = re.compile(r"^(Core|Working|Familiar):\s*(.*)$")


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


def _heading(doc, text):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(10)
    _run(para, text, bold=True, color=DARK_BLUE, size=12)
    return para


def cv_docx(rendered_text, identity, path):
    doc = _base_document()

    name_para = doc.add_paragraph()
    _run(name_para, (identity or {}).get("name", ""), bold=True, color=DARK_BLUE, size=24)

    headline = (identity or {}).get("headline")
    if headline:
        headline_para = doc.add_paragraph()
        _run(headline_para, headline, bold=True, color=MED_BLUE, size=10.5)

    contact = " | ".join(
        str(v) for v in [
            (identity or {}).get("location"),
            (identity or {}).get("phone"),
            (identity or {}).get("email"),
            (identity or {}).get("linkedin"),
        ] if v
    )
    if contact:
        contact_para = doc.add_paragraph()
        _run(contact_para, contact, bold=False, color=GRAY, size=9)

    lines = rendered_text.splitlines()
    if lines and lines[0].strip() == (identity or {}).get("name", ""):
        lines = lines[1:]

    section = None
    role_state = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if section == "PROFESSIONAL EXPERIENCE":
                role_state = "header"
            continue

        if stripped in HEADINGS:
            section = stripped
            role_state = None
            _heading(doc, stripped)
            continue

        if stripped.startswith("- "):
            content = stripped[2:]
            para = doc.add_paragraph(style="List Bullet")
            if section == "KEY PROJECTS" and ":" in content:
                label, _, rest = content.partition(":")
                _run(para, label + ":", bold=True, color=BLACK, size=9.5)
                _run(para, rest, bold=False, color=BLACK, size=9.5)
            else:
                _run(para, content, bold=False, color=BLACK, size=9.5)
            continue

        if section == "PROFESSIONAL EXPERIENCE" and role_state == "header":
            title, _, company = stripped.partition(", ")
            para = doc.add_paragraph()
            _run(para, title, bold=True, color=BLACK, size=11)
            _run(para, ", " + company, bold=False, color=MED_BLUE, size=11)
            role_state = "location"
            continue

        if section == "PROFESSIONAL EXPERIENCE" and role_state == "location":
            if stripped.startswith("Client: "):
                para = doc.add_paragraph()
                _run(para, stripped, bold=False, color=MED_BLUE, size=9.5)
                continue
            para = doc.add_paragraph()
            _run(para, stripped, bold=False, color=GRAY, size=9)
            role_state = None
            continue

        if section == "SKILLS":
            match = _TIER_LINE.match(stripped)
            if match:
                para = doc.add_paragraph()
                _run(para, match.group(1) + ": ", bold=True, color=DARK_BLUE, size=9.5)
                _run(para, match.group(2), bold=False, color=BLACK, size=9.5)
                continue

        if section == "EDUCATION" and "  -  " in stripped:
            degree, _, rest = stripped.partition("  -  ")
            para = doc.add_paragraph()
            _run(para, degree, bold=True, color=BLACK, size=9.5)
            _run(para, "  -  " + rest, bold=False, color=BLACK, size=9.5)
            continue

        para = doc.add_paragraph()
        _run(para, stripped, bold=False, color=BLACK, size=9.5)

    doc.save(str(path))
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
