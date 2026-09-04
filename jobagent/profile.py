import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from ruamel.yaml import YAML

TIERS = ("core", "working", "familiar")

_round_trip = YAML()
_round_trip.preserve_quotes = True
_round_trip.width = 4096
_round_trip.indent(mapping=2, sequence=4, offset=2)

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


def backup_master(path):
    """Copy master.yaml aside before it is replaced.

    A CV import rewrites the whole file, so there has to be a way back if the
    extraction misread something. Named the same way the database backups are,
    so they are obvious sitting next to each other in the folder.
    """
    file = Path(path)
    if not file.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = file.with_name(file.name + ".pre-cv-import-" + stamp + ".bak")
    shutil.copy2(file, target)
    return target


def write_master(path, data):
    """Replace master.yaml wholesale, keeping a backup of what was there.

    append_skills() edits one section in place and preserves the file's
    comments. This cannot: a CV import replaces the content entirely, so the
    header comment is written back explicitly rather than lost.
    """
    file = Path(path)
    backup = backup_master(path)
    with file.open("w", encoding="utf-8") as handle:
        handle.write(MASTER_HEADER)
        _round_trip.dump(data, handle)
    return backup


MASTER_HEADER = """# ---------------------------------------------------------------------------
# master.yaml - generated from the CV uploaded on the Profile screen.
#
# Edits made here are overwritten by the next CV upload. Change your CV and
# upload it again rather than editing this file by hand.
#
# Every bullet keeps a stable id. The tailor may only keep, reword, drop or
# pull bullets that exist here - it cannot invent new ones, and that guarantee
# is enforced in jobagent/documents/guard.py.
# ---------------------------------------------------------------------------

"""


def append_skills(path, additions):
    """Append new skill entries to master.yaml in place.

    additions is {tier: [{"name": ..., "context": ...}, ...]}. Uses a
    round-trip YAML loader so every other line in the file - formatting,
    comments, everything not touched here - comes back out identical.
    """
    file = Path(path)
    text = file.read_text(encoding="utf-8") if file.exists() else ""
    data = _round_trip.load(text) if text.strip() else {}
    if data is None:
        data = {}
    skills = data.setdefault("skills", {})
    for tier in TIERS:
        entries = additions.get(tier) or []
        if not entries:
            continue
        seq = skills.get(tier)
        if seq is None:
            seq = []
            skills[tier] = seq
        for entry in entries:
            row = {"name": entry["name"]}
            if entry.get("context"):
                row["context"] = entry["context"]
            seq.append(row)
    with file.open("w", encoding="utf-8") as f:
        _round_trip.dump(data, f)


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


def existing_names(master):
    names = set()
    for entries in skill_tiers(master).values():
        for entry in entries:
            names.add(entry["name"].strip().lower())
    return names


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
