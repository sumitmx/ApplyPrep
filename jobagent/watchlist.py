from pathlib import Path

import yaml

from .normalize import slugify

ATS_KINDS = ("greenhouse", "lever", "ashby", "workable")


def load(path="watchlist.yaml"):
    file = Path(path)
    if not file.exists():
        return []
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    out = []
    seen = set()
    for entry in data.get("companies") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled") is False:
            continue
        kind = str(entry.get("ats") or "").strip().lower()
        token = str(entry.get("token") or "").strip()
        if kind not in ATS_KINDS or not token:
            continue
        name = str(entry.get("name") or token).strip()
        key = (kind, token)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "ats": kind, "token": token, "slug": slugify(name)})
    return out


def by_kind(companies):
    grouped = {}
    for company in companies:
        grouped.setdefault(company["ats"], []).append(company)
    return grouped
