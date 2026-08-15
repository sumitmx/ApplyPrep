from . import agent, profile

EXTRACT_PROMPT = """You are helping someone log their skills for a CV database, from
their own free-form description. Return only a JSON object, no prose, no code fence.

Read the text below and pull out individual, concrete skills, tools, technologies,
methodologies or domains it names. Do not invent skills the text does not support.
Split combined mentions into separate entries (e.g. "Python and Docker" is two skills).
Skip anything already in the existing list below.

For each skill pick a tier:
  core     something they lead with, deep or recent hands-on experience
  working  solid hands-on experience, not their strongest suit
  familiar limited exposure, seen it, used it a little

Shape:
{"skills": [{"name": "<short skill name>", "tier": "core|working|familiar",
"context": "<short phrase, e.g. '3 years' or 'used in production', or null>"}]}

EXISTING SKILLS (do not repeat these)
{existing}

TEXT
{text}
"""

GAP_PROMPT = """You are helping someone spot skill gaps against real job postings
they are targeting. Return only a JSON object, no prose, no code fence.

Look at the job postings below. Name skills, tools or technologies that come up
more than once across them and are NOT already in the candidate's skill list.
Only name things the postings actually ask for, do not invent. Give at most 8,
ordered by how often they recur.

Shape:
{"gaps": [{"name": "<skill name>", "note": "<one short clause on where it came up>"}]}

CANDIDATE'S CURRENT SKILLS
{existing}

JOB POSTINGS
{postings}
"""


def _fill(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def extract(text, existing, timeout=agent.DEFAULT_TIMEOUT, provider=agent.DEFAULT_PROVIDER):
    text = (text or "").strip()
    if not text:
        raise agent.AgentError("Nothing to extract from.")
    prompt = _fill(EXTRACT_PROMPT, {
        "existing": ", ".join(sorted(existing)) or "(none yet)",
        "text": text[:4000],
    })
    data = agent.run_json(prompt, timeout, provider)
    out = []
    seen = set()
    for item in data.get("skills") or []:
        name = str(item.get("name") or "").strip()
        tier = str(item.get("tier") or "").strip().lower()
        if not name or tier not in profile.TIERS:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        context = item.get("context")
        out.append({
            "name": name,
            "tier": tier,
            "context": str(context).strip() if context else None,
        })
    return out


def find_gaps(postings, existing, timeout=agent.DEFAULT_TIMEOUT, provider=agent.DEFAULT_PROVIDER):
    if not (postings or "").strip():
        raise agent.AgentError("No recent job postings to compare against yet.")
    prompt = _fill(GAP_PROMPT, {
        "existing": ", ".join(sorted(existing)) or "(none yet)",
        "postings": postings[:8000],
    })
    data = agent.run_json(prompt, timeout, provider)
    out = []
    seen = set(existing)
    for item in data.get("gaps") or []:
        name = str(item.get("name") or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        note = str(item.get("note") or "").strip()
        out.append({"name": name, "note": note or None})
    return out[:8]


def merge(master, entries):
    """Validate and dedup proposed skill entries against the current profile.

    Returns (additions, added, skipped) where additions is {tier: [{"name",
    "context"}, ...]} - the entries that should actually be appended -
    suitable for profile.append_skills(). Does not touch master itself.
    """
    existing = profile.existing_names(master)
    additions = {tier: [] for tier in profile.TIERS}
    added, skipped = [], []
    for entry in entries or []:
        name = str((entry or {}).get("name") or "").strip()
        tier = str((entry or {}).get("tier") or "").strip().lower()
        if not name or tier not in profile.TIERS:
            skipped.append({"name": name, "reason": "invalid"})
            continue
        key = name.lower()
        if key in existing:
            skipped.append({"name": name, "reason": "duplicate"})
            continue
        existing.add(key)
        row = {"name": name}
        context = (entry or {}).get("context")
        if context:
            row["context"] = str(context).strip()
        additions[tier].append(row)
        added.append({"name": name, "tier": tier})
    return additions, added, skipped
