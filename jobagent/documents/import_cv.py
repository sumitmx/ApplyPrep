"""Rebuild master.yaml from the CV the candidate uploaded.

master.yaml used to be hand-written, and the uploaded CV was stored but never
read. This closes that gap: the upload is the source of truth, and everything
downstream - tailoring, ATS coverage, the skills panel, job rating - already
reads master.yaml, so updating it here updates all of them at once.

Two rules shape the whole module.

Bullets are copied verbatim. They end up as the text of real CVs that get sent
to employers, and guard.py exists specifically to stop invented content
reaching a document. If the import paraphrased on the way in, the guard would
be checking tailored output against already-fabricated material and the
protection would be worthless. Anything the model returns that is not actually
present in the uploaded CV is dropped, not trusted.

Bullet ids are kept stable where the text still matches. The tailor records
which bullet it kept or dropped by id, so churning ids on every upload would
quietly orphan that history.
"""

import json
import re
import unicodedata

from rapidfuzz import fuzz

from .. import agent

# Below this, two bullets are different bullets and the new one gets a new id.
# Deliberately high: a wrong match silently transplants one bullet's history
# onto another, which is worse than simply minting a fresh id.
ID_MATCH_THRESHOLD = 88

# A bullet the model returns has to actually appear in the uploaded CV. The
# threshold is lower than the id match because a CV's plain-text extraction
# introduces line breaks and stray spacing that the model tidies up.
VERBATIM_THRESHOLD = 82

# Reading a whole CV is a far bigger call than rating one job or pulling a few
# skills out of pasted text: the entire CV goes in and an entire structured
# profile comes back. Measured runs land between three and five minutes, which
# straddles the shared 240s default, so this gets its own generous ceiling.
# Timing out here is expensive - it throws away a wait the candidate has
# already sat through - so the limit is set well clear of normal, not near it.
IMPORT_TIMEOUT = 900

TIERS = ("core", "working", "familiar")

PROMPT = """You are reading someone's CV and turning it into structured data for
their own job-search tool. This is their file, about them, on their machine.

Return ONLY a JSON object, no prose and no code fence, with these keys:

{
  "identity": {"name": "", "headline": "", "location": "", "email": "",
               "phone": "", "linkedin": ""},
  "summary": "",
  "experience": [
    {"company": "", "client": "", "title": "", "location": "",
     "start": "YYYY-MM", "end": "YYYY-MM or present",
     "bullets": [{"text": "", "skills": ["lowercase", "tags"]}]}
  ],
  "projects": [{"name": "", "text": "", "skills": ["lowercase", "tags"]}],
  // one entry per project - if a project has several bullets in the CV, join
  // them into its single "text". Never emit the same project name twice.
  "skills": {
    "core":     [{"name": "", "context": ""}],
    "working":  [{"name": "", "context": ""}],
    "familiar": [{"name": "", "context": ""}]
  },
  "certifications": [""],
  "education": [{"degree": "", "school": "", "years": ""}],
  "languages": [{"name": "", "level": ""}]
}

THE ONE RULE THAT MATTERS: every "text" field in experience bullets and
projects must be copied WORD FOR WORD from the CV. Do not improve, shorten,
rephrase, merge or fix the grammar of a bullet. You may fix nothing but
obvious line-break artefacts from the file conversion. These bullets become
the text of real CVs this person sends to employers, so a sentence you wrote
would be putting words in their mouth. If a bullet is awkward, copy it
awkwardly.

Everything else you may compose:
- "summary" may be taken from the CV's own profile paragraph if it has one.
- "skills" tiers are your judgement: "core" is what they would defend in a
  deep-dive interview, usually what recurs across roles and years; "working"
  is what they have clearly shipped with; "familiar" is honest exposure only.
  "context" is a short phrase of evidence from the CV, like "10 yr, banking"
  or "CI/CD at two employers". Only list a skill the CV actually supports.
- "skills" tags on bullets are short lowercase keywords for matching.

ONE TECHNOLOGY PER SKILL ENTRY. These names are matched word-for-word against
job adverts, so a grouped entry matches nothing. Write "BigQuery" and "Looker"
as two entries, never "BigQuery / Looker"; "Jenkins" and "GitLab", never
"CI/CD (Jenkins, GitLab)". Names that genuinely contain a slash, like "CI/CD"
or "Node.js", are single entries and stay as they are.

"projects" is for personal or side projects the CV lists under its own
projects section. Work delivered for an employer belongs in that employer's
bullets, not here. Keep every bullet the CV lists under a role with that role.

Leave a field as "" or [] when the CV does not say. Never guess an email,
phone number or date. Dates are YYYY-MM; use "present" for a current role.

CV TEXT
{cv_text}
"""


def _norm(text):
    """Comparable form of a bullet: case, accents and spacing folded away."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _squash(text):
    return " ".join(_norm(text).split())


def slug(text, fallback="item"):
    out = re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-")
    return (out or fallback)[:40]


def extract(cv_text, timeout=IMPORT_TIMEOUT, provider=agent.DEFAULT_PROVIDER):
    """Ask the model to turn CV text into the master.yaml shape."""
    if not (cv_text or "").strip():
        raise ValueError("the uploaded CV has no readable text")
    prompt = PROMPT.replace("{cv_text}", cv_text.strip())
    data = agent.run_json(prompt, timeout, provider)
    if not isinstance(data, dict):
        raise ValueError("the model did not return a CV object")
    return data


def _verbatim(text, haystack):
    """Is this sentence really in the CV, or did the model write it?"""
    needle = _squash(text)
    if not needle:
        return False
    if needle in haystack:
        return True
    return fuzz.partial_ratio(needle, haystack) >= VERBATIM_THRESHOLD


def _existing_bullets(master):
    """{normalised text: id} for everything master.yaml already knows."""
    found = {}
    for role in (master or {}).get("experience") or []:
        for bullet in role.get("bullets") or []:
            if isinstance(bullet, dict) and bullet.get("id"):
                found[_squash(bullet.get("text"))] = str(bullet["id"])
    for project in (master or {}).get("projects") or []:
        if project.get("id"):
            found[_squash(project.get("text"))] = str(project["id"])
    return found


def _reuse_id(text, known, claimed):
    """The id this text had last time, if it is recognisably the same text."""
    target = _squash(text)
    if not target:
        return None
    best, score = None, 0
    for old_text, old_id in known.items():
        if old_id in claimed:
            continue
        ratio = fuzz.ratio(target, old_text)
        if ratio > score:
            best, score = old_id, ratio
    return best if score >= ID_MATCH_THRESHOLD else None


# Skill names are matched against job adverts with a word-boundary pattern
# built from the whole name, so a compound entry like "BigQuery / Looker"
# matches an advert saying "BigQuery" - never. Models like to group related
# tools, so grouped names are split back apart before they can quietly kill
# the gate's skill-overlap check, ATS coverage and job rating.
#
# " / " with spaces separates two tools; "CI/CD" and "Node.js" have no spaces
# and stay whole. A trailing "(Jenkins, GitLab)" is a list of its own.
#
# "and" and "&" are deliberately NOT separators: "Team & Programme Leadership"
# and "Research and Development" are single skills, and splitting them would
# invent two half-skills that match nothing. Only punctuation that genuinely
# means "these are separate items" is treated as a separator.
_GROUPED = re.compile(r"\s+/\s+|\s*,\s*")
_PARENS = re.compile(r"\(([^)]*)\)")


def split_skill_name(name):
    """One entry per technology, so each can match an advert on its own."""
    name = str(name or "").strip()
    if not name:
        return []
    inner = _PARENS.findall(name)
    outer = _PARENS.sub(" ", name)
    parts = []
    for chunk in [outer] + inner:
        for piece in _GROUPED.split(chunk):
            piece = piece.strip(" -–—")
            if piece:
                parts.append(piece)
    return parts or [name]


def _clean_skills(raw):
    tiers = {}
    seen = set()
    for tier in TIERS:
        rows = []
        for entry in (raw or {}).get(tier) or []:
            if not isinstance(entry, dict):
                continue
            context = str(entry.get("context") or "").strip()
            for name in split_skill_name(entry.get("name")):
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                row = {"name": name}
                if context:
                    row["context"] = context
                rows.append(row)
        tiers[tier] = rows
    return tiers


def build(extracted, previous, cv_text):
    """Turn a model response into master.yaml content, with a change summary.

    `previous` is the master.yaml being replaced - used only to carry stable
    bullet ids across, never to keep content the new CV has dropped.
    """
    haystack = _squash(cv_text)
    known = _existing_bullets(previous)
    claimed = set()
    dropped_bullets = 0

    experience = []
    for index, role in enumerate(extracted.get("experience") or [], start=1):
        if not isinstance(role, dict):
            continue
        company = str(role.get("company") or "").strip()
        role_id = "exp." + slug(company, "role" + str(index))
        bullets = []
        for position, bullet in enumerate(role.get("bullets") or [], start=1):
            text = str((bullet or {}).get("text") or "").strip() if isinstance(bullet, dict) else ""
            if not text:
                continue
            if not _verbatim(text, haystack):
                dropped_bullets += 1
                continue
            bullet_id = _reuse_id(text, known, claimed) or (role_id + ".b" + str(position))
            claimed.add(bullet_id)
            row = {"id": bullet_id, "text": text}
            tags = [str(t).strip().lower() for t in (bullet.get("skills") or []) if str(t).strip()]
            if tags:
                row["skills"] = tags
            bullets.append(row)
        if not bullets:
            continue
        entry = {"id": role_id, "company": company}
        for key in ("client", "title", "location", "start", "end"):
            value = str(role.get(key) or "").strip()
            if value:
                entry[key] = value
        entry["bullets"] = bullets
        experience.append(entry)

    projects = []
    by_name = {}
    for index, project in enumerate(extracted.get("projects") or [], start=1):
        if not isinstance(project, dict):
            continue
        text = str(project.get("text") or "").strip()
        name = str(project.get("name") or "").strip()
        if not text or not name:
            continue
        if not _verbatim(text, haystack):
            dropped_bullets += 1
            continue
        tags = [str(t).strip().lower() for t in (project.get("skills") or []) if str(t).strip()]
        # One project, one entry. Models tend to emit a project's bullets as
        # separate projects, which turns four projects into twenty-four; the
        # repeats are folded back into the project they belong to.
        merged = by_name.get(name.lower())
        if merged:
            merged["text"] = merged["text"].rstrip(". ") + ". " + text
            for tag in tags:
                if tag not in merged.setdefault("skills", []):
                    merged["skills"].append(tag)
            continue
        project_id = _reuse_id(text, known, claimed) or ("proj." + slug(name, "p" + str(index)))
        claimed.add(project_id)
        row = {"id": project_id, "name": name, "text": text}
        if tags:
            row["skills"] = tags
        by_name[name.lower()] = row
        projects.append(row)

    identity = {}
    for key in ("name", "headline", "location", "email", "phone", "linkedin"):
        value = str((extracted.get("identity") or {}).get(key) or "").strip()
        if value:
            identity[key] = value

    master = {
        "identity": identity,
        "summary": str(extracted.get("summary") or "").strip(),
        "experience": experience,
        "projects": projects,
        "skills": _clean_skills(extracted.get("skills")),
        "certifications": [str(c).strip() for c in extracted.get("certifications") or [] if str(c).strip()],
        "education": [e for e in extracted.get("education") or [] if isinstance(e, dict)],
        "languages": [l for l in extracted.get("languages") or [] if isinstance(l, dict)],
        # Keywords spotted in job adverts are about the job market, not about
        # the CV, so a re-import has no business clearing them.
        "pending_keywords": (previous or {}).get("pending_keywords") or [],
    }
    return master, summarise(previous, master, dropped_bullets)


def _skill_names(master):
    names = {}
    for tier in TIERS:
        for entry in ((master or {}).get("skills") or {}).get(tier) or []:
            names[str(entry.get("name", "")).lower()] = entry.get("name")
    return names


def _bullet_count(master):
    total = len((master or {}).get("projects") or [])
    for role in (master or {}).get("experience") or []:
        total += len(role.get("bullets") or [])
    return total


def summarise(previous, current, dropped_bullets=0):
    """What actually changed, in terms worth showing the candidate."""
    before, after = _skill_names(previous), _skill_names(current)
    kept_ids = {b["id"] for role in current.get("experience") or []
                for b in role.get("bullets") or []}
    kept_ids |= {p["id"] for p in current.get("projects") or []}
    old_ids = set(_existing_bullets(previous).values())

    return {
        "skills_added": sorted(after[k] for k in after.keys() - before.keys()),
        "skills_removed": sorted(before[k] for k in before.keys() - after.keys()),
        "roles": len(current.get("experience") or []),
        "roles_before": len((previous or {}).get("experience") or []),
        "bullets": _bullet_count(current),
        "bullets_before": _bullet_count(previous),
        "bullet_ids_kept": len(kept_ids & old_ids),
        "bullets_not_in_cv": dropped_bullets,
        "identity_changed": sorted(
            key for key in ("name", "headline", "location", "email", "phone", "linkedin")
            if ((previous or {}).get("identity") or {}).get(key)
            != (current.get("identity") or {}).get(key)
        ),
        "summary_changed": (str((previous or {}).get("summary") or "").strip()
                            != current.get("summary", "")),
    }


def validate(master):
    """Refuse to write something that would leave the app worse off."""
    problems = []
    if not (master.get("identity") or {}).get("name"):
        problems.append("no name was found in the CV")
    if not master.get("experience"):
        problems.append("no work experience was found in the CV")
    if _bullet_count(master) == 0:
        # guard.check raises on an empty master, so tailoring would be dead.
        problems.append("no bullets survived - the CV text may not have extracted properly")
    return problems


def json_preview(master):
    return json.dumps(master, indent=2, ensure_ascii=False)
