from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate

from . import palette

GRAY = "#595959"
BLACK = "#000000"
WHITE = "#FFFFFF"


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles(accent_hex):
    ink = palette.ink_for(accent_hex)
    on_paper = palette.on_paper(accent_hex)
    return {
        "name": ParagraphStyle(
            "name", fontName="Helvetica-Bold", fontSize=24,
            textColor=HexColor(ink), backColor=HexColor(accent_hex),
            leading=28, spaceAfter=0, spaceBefore=0, borderPadding=(6, 10, 2, 10),
        ),
        "headline": ParagraphStyle(
            "headline", fontName="Helvetica-Bold", fontSize=10.5,
            textColor=HexColor(ink), backColor=HexColor(accent_hex),
            spaceAfter=0, spaceBefore=0, borderPadding=(0, 10, 2, 10),
        ),
        "contact": ParagraphStyle(
            "contact", fontName="Helvetica", fontSize=9,
            textColor=HexColor(ink), backColor=HexColor(accent_hex),
            spaceAfter=8, spaceBefore=0, borderPadding=(0, 10, 6, 10),
        ),
        "heading": ParagraphStyle(
            "heading", fontName="Helvetica-Bold", fontSize=12,
            textColor=HexColor(ink), backColor=HexColor(accent_hex),
            spaceBefore=10, spaceAfter=4, borderPadding=(4, 10, 4, 10),
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9.5,
            textColor=HexColor(BLACK), leading=13, spaceAfter=2,
        ),
        "role_meta": ParagraphStyle(
            "role_meta", fontName="Helvetica", fontSize=9,
            textColor=HexColor(GRAY), spaceAfter=2,
        ),
        "client": ParagraphStyle(
            "client", fontName="Helvetica", fontSize=9.5,
            textColor=HexColor(on_paper), spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9.5,
            textColor=HexColor(BLACK), leading=13,
        ),
    }


def _bullets(items, style):
    return ListFlowable(
        [ListItem(Paragraph(text, style), leftIndent=6) for text in items],
        bulletType="bullet",
        leftIndent=16,
        spaceAfter=4,
    )


def cv_pdf(content, path, accent=palette.DEFAULT_ACCENT):
    accent_hex = palette.resolve(accent)["hex"]
    _on_paper = palette.on_paper(accent_hex)
    styles = _styles(accent_hex)
    identity = content.get("identity") or {}

    target = path if hasattr(path, "write") else str(path)
    doc = SimpleDocTemplate(
        target, pagesize=LETTER,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        title=identity.get("name") or "CV",
    )

    flow = [Paragraph(_esc(identity.get("name", "")), styles["name"])]

    headline = identity.get("headline")
    if headline:
        flow.append(Paragraph(_esc(headline), styles["headline"]))

    contact = " | ".join(
        _esc(str(v)) for v in [
            identity.get("location"), identity.get("phone"),
            identity.get("email"), identity.get("linkedin"),
        ] if v
    )
    if contact:
        flow.append(Paragraph(contact, styles["contact"]))

    summary = content.get("summary")
    if summary:
        flow.append(Paragraph("PROFESSIONAL SUMMARY", styles["heading"]))
        flow.append(Paragraph(_esc(summary), styles["body"]))

    for section in content.get("sections") or []:
        kind = section["kind"]
        flow.append(Paragraph(section["heading"], styles["heading"]))

        if kind == "skills":
            for tier in section["tiers"]:
                text = (
                    '<font color="' + _on_paper + '"><b>' + _esc(tier["label"]) + ': </b></font>'
                    + _esc(", ".join(tier["items"]))
                )
                flow.append(Paragraph(text, styles["body"]))

        elif kind == "experience":
            for role in section["roles"]:
                header = (
                    "<b>" + _esc(role["title"]) + "</b>, <font color=\"" + _on_paper + "\">"
                    + _esc(role["company"]) + "</font>"
                )
                flow.append(Paragraph(header, styles["body"]))
                if role.get("client"):
                    flow.append(Paragraph("Client: " + _esc(role["client"]), styles["client"]))
                location = role.get("location") or ""
                meta = (location + "    " if location else "") + role["period"]
                flow.append(Paragraph(_esc(meta), styles["role_meta"]))
                flow.append(_bullets(role["bullets"], styles["bullet"]))

        elif kind == "projects":
            texts = [
                "<b>" + _esc(item["name"]) + ":</b> " + _esc(item["text"])
                for item in section["items"]
            ]
            flow.append(_bullets(texts, styles["bullet"]))

        elif kind == "education":
            for item in section["items"]:
                text = (
                    "<b>" + _esc(item["degree"]) + "</b>  -  " + _esc(item["school"])
                    + " (" + _esc(item["years"]) + ")"
                )
                flow.append(Paragraph(text, styles["body"]))

        elif kind == "certifications":
            flow.append(_bullets([_esc(item) for item in section["items"]], styles["bullet"]))

        elif kind == "languages":
            texts = [
                (lang["name"] + " (" + lang["level"] + ")") if lang.get("level") else lang["name"]
                for lang in section["items"]
            ]
            flow.append(_bullets([_esc(t) for t in texts], styles["bullet"]))

        elif kind == "highlights":
            flow.append(_bullets([_esc(item) for item in section["items"]], styles["bullet"]))

    doc.build(flow)
    return path
