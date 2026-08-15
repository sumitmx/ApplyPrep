from .. import agent
from . import coverage, guard, lint

_TYPOGRAPHIC = {
    "–": "-", "—": "-",
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...",
    " ": " ",
}


def _ascii_safe(text):
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


def render_cv(changes, master):
    decided = {c["id"] for c in changes}
    keep = {c["id"]: c for c in changes if c["action"] != "dropped"}
    _ensure_every_role_survives(keep, master, decided)
    lines = [
        (master.get("identity") or {}).get("name", ""),
        "",
        "PROFESSIONAL SUMMARY",
        (master.get("summary") or "").strip(),
    ]
    lines += ["", "SKILLS"]
    for tier in ("core", "working", "familiar"):
        names = []
        for entry in (master.get("skills") or {}).get(tier) or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name:
                names.append(str(name))
        if names:
            lines.append(tier.title() + ": " + ", ".join(names))
    lines += ["", "PROFESSIONAL EXPERIENCE"]
    for role in master.get("experience") or []:
        chosen = [b for b in (role.get("bullets") or []) if b.get("id") in keep]
        if not chosen:
            continue
        lines.append("")
        lines.append(role.get("title", "") + ", " + role.get("company", ""))
        if role.get("client"):
            lines.append("Client: " + role["client"])
        location = role.get("location") or ""
        lines.append((location + "    " if location else "") + _period(role))
        for bullet in chosen:
            lines.append("- " + keep[bullet["id"]]["text"])
    projects = [p for p in (master.get("projects") or []) if p.get("id") in keep]
    if projects:
        lines += ["", "KEY PROJECTS"]
        for project in projects:
            lines.append("- " + project.get("name", "") + ": " + keep[project["id"]]["text"])
    lines += ["", "EDUCATION"]
    for item in master.get("education") or []:
        lines.append(item.get("degree", "") + "  -  " + item.get("school", "")
                     + " (" + str(item.get("years", "")) + ")")
    certifications = master.get("certifications") or []
    if certifications:
        lines += ["", "CERTIFICATIONS"]
        lines.append(", ".join(str(c) for c in certifications))
    languages = master.get("languages") or []
    if languages:
        lines += ["", "LANGUAGES"]
        lines.append(", ".join(
            (str(lang.get("name", "")) + " (" + str(lang.get("level", "")) + ")")
            if isinstance(lang, dict) else str(lang)
            for lang in languages
        ))
    return _ascii_safe("\n".join(lines))


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
    rendered = render_cv(changes, master)
    return {
        "changes": changes,
        "note": data.get("note"),
        "rendered": rendered,
        "parse_safety": lint.check(rendered, changes),
        "keywords": coverage.analyse(job.get("description"), rendered, master),
        "counts": {
            action: sum(1 for c in changes if c["action"] == action)
            for action in guard.ACTIONS
        },
    }


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
