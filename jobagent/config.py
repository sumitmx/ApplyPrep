import copy
import os
from pathlib import Path

import yaml

DEFAULTS = {
    "db_path": "jobs.db",
    "port": 8756,
    "master_path": "master.yaml",
    "profile_path": "profile.yaml",
    "watchlist_path": "watchlist.yaml",
    "countries": ["DE", "NL"],
    "since_days": 14,
    "reach": {
        "blue_card_eur": 48300,
        "factors": {"confirmed": 1.0, "unknown": 0.55, "denied": 0.05},
        "weights": {
            "language": 20,
            "employer": 20,
            "freshness": 20,
            "location": 20,
            "salary": 20,
        },
    },
    "bands": {
        "strong_match": 70,
        "strong_chance": 50,
        "medium_match": 45,
        "medium_chance": 45,
    },
    "gate": {
        "sponsor_bypass_title": True,
        "min_salary_eur": None,
        "require_english_only": False,
        "allow_contract": True,
        "max_age_days": 45,
        "title_must_match": [
            "architect",
            "automation",
            "rpa",
            "ai engineer",
            "platform lead",
            "principal engineer",
        ],
        "title_must_not_match": [
            "intern",
            "graduate",
            "working student",
            "werkstudent",
            "praktikum",
        ],
    },
    "sources": {
        "arbeitnow": {"enabled": True},
        "remotive": {"enabled": True, "region_filter": True},
        "remoteok": {"enabled": True, "region_filter": True},
        "wwr": {"enabled": True, "region_filter": True},
        "adzuna": {"enabled": False, "app_id": None, "app_key": None},
        "greenhouse": {"enabled": True, "region_filter": True, "pause_seconds": 0.4},
        "lever": {"enabled": True, "region_filter": True, "pause_seconds": 0.4},
        "ashby": {"enabled": True, "region_filter": True, "pause_seconds": 0.4},
        "workable": {"enabled": True, "region_filter": True, "pause_seconds": 1.0},
    },
    "gmail": {
        "enabled": False,
        "client_secret_path": "gmail_client_secret.json",
        "lookback_days": 90,
    },
}


def merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path="config.yaml"):
    cfg = copy.deepcopy(DEFAULTS)
    file = Path(path)
    if file.exists():
        cfg = merge(cfg, yaml.safe_load(file.read_text()) or {})
    adzuna = cfg["sources"]["adzuna"]
    adzuna["app_id"] = adzuna["app_id"] or os.environ.get("ADZUNA_APP_ID")
    adzuna["app_key"] = adzuna["app_key"] or os.environ.get("ADZUNA_APP_KEY")
    if adzuna["app_id"] and adzuna["app_key"]:
        adzuna["enabled"] = True
    return cfg
