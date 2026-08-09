import re
from pathlib import Path

import yaml

TIERS = ("core", "working", "familiar")

_SEPARATOR = r"[\s\-/_.]+"
_SKILL_PATTERNS = {}


def _skill_pattern(name):
    cached = _SKILL_PATTERNS.get(name)
    if cached is None:
        words = [re.escape(w) for w in name.lower().split() if w]
        if not words:
            return None
        body = _SEPARATOR.join(words)
        cached = re.compile(r"(?<!\w)" + body + r"(?!\w)")
        _SKILL_PATTERNS[name] = cached
    return cached


def _load(path):
    file = Path(path)
    if not file.exists():
        return None
    return yaml.safe_load(file.read_text(encoding="utf-8")) or {}


def load_master(path="master.yaml"):
    return _load(path)


def load_profile(path="profile.yaml"):
    return _load(path)


def skill_tiers(master):
    if not master:
        return {tier: [] for tier in TIERS}
    skills = master.get("skills") or {}
    out = {}
    for tier in TIERS:
        entries = []
        for item in skills.get(tier) or []:
            if isinstance(item, dict):
                name = item.get("name")
                context = item.get("context") or item.get("years")
            else:
                name = item
                context = None
            if name:
                entries.append({"name": str(name), "context": _text(context)})
        out[tier] = entries
    return out


def _text(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value) + " yr"
    return str(value)


def bullet_ids(master):
    if not master:
        return set()
    found = set()
    for role in master.get("experience") or []:
        for bullet in role.get("bullets") or []:
            if isinstance(bullet, dict) and bullet.get("id"):
                found.add(str(bullet["id"]))
    return found


def match_skills(master, text):
    tiers = skill_tiers(master)
    low = (text or "").lower()
    matched = {tier: [] for tier in TIERS}
    for tier, entries in tiers.items():
        for entry in entries:
            pattern = _skill_pattern(entry["name"])
            if pattern and pattern.search(low):
                matched[tier].append(entry)
    return matched
