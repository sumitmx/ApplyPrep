from .. import agent
from . import coverage, guard, lint

_TYPOGRAPHIC = {
    "–": "-", "—": "-",
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...",
    " ": " ",
}


def ascii_safe(text):
    for char, replacement in _TYPOGRAPHIC.items():
        text = text.replace(char, replacement)
    return text

CV_PROMPT = """You are tailoring an existing CV for one specific job. Return only
a JSON object, no prose, no code fence.

Absolute rule: you may only reference bullet ids from the list below. You may
reword a bullet, you may not invent a project, an employer, a technology or a
number that is not already there. Anything you invent will be rejected by code.

Shape:
{"changes": [{"id": "<bullet id>", "action": "kept|rewrote|dropped|pulled",
"text": "<final wording, required for rewrote and pulled>",
"reason": "<short why, one clause>"}], "note": "<one sentence on your approach>"}

Actions:
  kept    the bullet stays as written
  rewrote same fact, wording moved closer to the posting's language
  dropped not relevant to this posting, leave it out
  pulled  a bullet not usually near the top, surfaced because this job asks for it

Include every bullet you want on the tailored CV plus the ones you drop. Aim for
eight to twelve entries in total.

AVAILABLE BULLETS
{bullets}

CANDIDATE SKILL TIERS
{tiers}

THE JOB
Title: {title}
Company: {company}
Location: {location}

{description}
"""

LETTER_PROMPT = """Write a cover letter for this job. Return only a JSON object,
no prose, no code fence.

Shape:
{"body": "<the letter, paragraphs separated by a blank line>",
"note": "<one sentence on the angle you took>"}

Rules:
  Under {max_words} words. No greeting line, no sign off, code adds those.
  Every claim must come from the CV facts below. Invent nothing.
  State plainly that the candidate needs visa sponsorship and is relocating.
  If there is a real skill gap for this job, name it once, honestly, without
  apologising, then move on.
  One specific sentence about this company, not a template line.
  Plain direct sentences. No buzzwords, no "passionate", no "leverage".

CANDIDATE
{summary}

CV FACTS AVAILABLE
{bullets}

SKILL TIERS
{tiers}

THE JOB
Title: {title}
Company: {company}
Location: {location}

{description}
"""


def _bullet_list(master):
    lines = []
    for bullet_id, data in guard.known_bullets(master).items():
        lines.append(bullet_id + " [" + (data["company"] or "") + "] " + data["text"])
    return "\n".join(lines)


def _tier_list(master):
    lines = []
    for tier in ("core", "working", "familiar"):
        for entry in (master.get("skills") or {}).get(tier) or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            context = entry.get("context") if isinstance(entry, dict) else None
            lines.append(tier + ": " + str(name) + (" (" + str(context) + ")" if context else ""))
    return "\n".join(lines)


def _fill(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _period(role):
    def fmt(value):
        text = str(value or "")
        if text.lower() == "present":
            return "Present"
        parts = text.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            index = int(parts[1])
            if 1 <= index <= 12:
                return MONTHS[index - 1] + " " + parts[0]
        return text
    return fmt(role.get("start")) + " - " + fmt(role.get("end"))


def _ensure_every_role_survives(keep, master, decided):
    for role in master.get("experience") or []:
        role_bullets = role.get("bullets") or []
        if role_bullets and not any(b.get("id") in decided for b in role_bullets):
            first = role_bullets[0]
            keep[first["id"]] = {
                "id": first["id"], "action": "kept", "text": first["text"],
            }


def build_cv_content(changes, master):
    decided = {c["id"] for c in changes}
    keep = {c["id"]: c for c in changes if c["action"] != "dropped"}
    _ensure_every_role_survives(keep, master, decided)

    raw_identity = master.get("identity") or {}
    identity = {
        key: (ascii_safe(str(value)) if value is not None else value)
        for key, value in raw_identity.items()
    }

    tiers = []
    for tier in ("core", "working", "familiar"):
        names = []
        for entry in (master.get("skills") or {}).get(tier) or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name:
                names.append(ascii_safe(str(name)))
        if names:
            tiers.append({"label": tier.title(), "items": names})

    roles = []
    for role in master.get("experience") or []:
        chosen = [b for b in (role.get("bullets") or []) if b.get("id") in keep]
        if not chosen:
            continue
        roles.append({
            "title": ascii_safe(role.get("title", "")),
            "company": ascii_safe(role.get("company", "")),
            "client": ascii_safe(role["client"]) if role.get("client") else None,
            "location": ascii_safe(role.get("location") or ""),
            "period": ascii_safe(_period(role)),
            "bullets": [ascii_safe(keep[b["id"]]["text"]) for b in chosen],
        })

    projects = []
    for project in master.get("projects") or []:
        if project.get("id") in keep:
            projects.append({
                "name": ascii_safe(project.get("name", "")),
                "text": ascii_safe(keep[project["id"]]["text"]),
            })

    education = [
        {
            "degree": ascii_safe(item.get("degree", "")),
            "school": ascii_safe(item.get("school", "")),
            "years": ascii_safe(str(item.get("years", ""))),
        }
        for item in master.get("education") or []
    ]

    certifications = [ascii_safe(str(c)) for c in (master.get("certifications") or [])]

    languages = []
    for lang in master.get("languages") or []:
        if isinstance(lang, dict):
            languages.append({
                "name": ascii_safe(str(lang.get("name", ""))),
                "level": ascii_safe(str(lang.get("level", ""))) if lang.get("level") else None,
            })
        else:
            languages.append({"name": ascii_safe(str(lang)), "level": None})

    sections = [
        {"kind": "skills", "heading": "SKILLS", "tiers": tiers},
        {"kind": "experience", "heading": "PROFESSIONAL EXPERIENCE", "roles": roles},
    ]
    if projects:
        sections.append({"kind": "projects", "heading": "KEY PROJECTS", "items": projects})
    sections.append({"kind": "education", "heading": "EDUCATION", "items": education})
    if certifications:
        sections.append({"kind": "certifications", "heading": "CERTIFICATIONS", "items": certifications})
    if languages:
        sections.append({"kind": "languages", "heading": "LANGUAGES", "items": languages})

    return {
        "identity": identity,
        "summary": ascii_safe((master.get("summary") or "").strip()),
        "sections": sections,
    }


def flatten_cv(content):
    identity = content.get("identity") or {}
    lines = [
        identity.get("name", ""),
        "",
        "PROFESSIONAL SUMMARY",
        content.get("summary") or "",
    ]
    for section in content.get("sections") or []:
        lines += ["", section["heading"]]
        kind = section["kind"]
        if kind == "skills":
            for tier in section["tiers"]:
                lines.append(tier["label"] + ": " + ", ".join(tier["items"]))
        elif kind == "experience":
            for role in section["roles"]:
                lines.append("")
                lines.append(role["title"] + ", " + role["company"])
                if role.get("client"):
                    lines.append("Client: " + role["client"])
                location = role.get("location") or ""
                lines.append((location + "    " if location else "") + role["period"])
                for bullet in role["bullets"]:
                    lines.append("- " + bullet)
        elif kind == "projects":
            for item in section["items"]:
                lines.append("- " + item["name"] + ": " + item["text"])
        elif kind == "education":
            for item in section["items"]:
                lines.append(item["degree"] + "  -  " + item["school"]
                             + " (" + item["years"] + ")")
        elif kind == "certifications":
            lines.append(", ".join(section["items"]))
        elif kind == "languages":
            lines.append(", ".join(
                (lang["name"] + " (" + lang["level"] + ")") if lang.get("level") else lang["name"]
                for lang in section["items"]
            ))
        elif kind == "highlights":
            for item in section["items"]:
                lines.append("- " + item)
    return "\n".join(lines)


def render_cv(changes, master):
    return flatten_cv(build_cv_content(changes, master))


def tailor_cv(job, master, timeout=agent.DEFAULT_TIMEOUT,
              provider=agent.DEFAULT_PROVIDER):
    prompt = _fill(CV_PROMPT, {
        "bullets": _bullet_list(master),
        "tiers": _tier_list(master),
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location": ", ".join(x for x in [job.get("city"), job.get("country")] if x),
        "description": (job.get("description") or "")[:6000],
    })
    data = agent.run_json(prompt, timeout, provider)
    changes = guard.check(data.get("changes"), master)
    content = build_cv_content(changes, master)
    rendered = flatten_cv(content)
    keywords = coverage.analyse(job.get("description"), rendered, master)
    return {
        "changes": changes,
        "note": data.get("note"),
        "rendered": rendered,
        "structured": content,
        "parse_safety": lint.check(rendered, changes),
        "keywords": keywords,
        "ats_score": _ats_score(keywords["counts"]),
        "counts": {
            action: sum(1 for c in changes if c["action"] == action)
            for action in guard.ACTIONS
        },
    }


def _ats_score(counts):
    total = counts["covered"] + counts["fixable"] + counts["real_gap"]
    if not total:
        return None
    return round(counts["covered"] / total * 100)


def cover_letter(job, master, profile, timeout=agent.DEFAULT_TIMEOUT,
                  provider=agent.DEFAULT_PROVIDER):
    max_words = ((profile or {}).get("cover_letter") or {}).get("max_words", 250)
    prompt = _fill(LETTER_PROMPT, {
        "max_words": max_words,
        "summary": master.get("summary") or "",
        "bullets": _bullet_list(master),
        "tiers": _tier_list(master),
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location": ", ".join(x for x in [job.get("city"), job.get("country")] if x),
        "description": (job.get("description") or "")[:6000],
    })
    data = agent.run_json(prompt, timeout, provider)
    body = (data.get("body") or "").strip()
    if not body:
        raise agent.AgentError("Claude returned an empty letter.")
    words = len(body.split())
    return {
        "body": body,
        "note": data.get("note"),
        "word_count": words,
        "over_limit": words > max_words,
        "max_words": max_words,
    }
