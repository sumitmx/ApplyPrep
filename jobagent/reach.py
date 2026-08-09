from datetime import datetime, timezone

from .normalize import COUNTRY_NAMES

EUROPEAN = set(COUNTRY_NAMES.values())

WEAK_GERMAN = {"", "none", "a1", "a2", "basic"}

DEFAULTS = {
    "blue_card_eur": 48300,
    "factors": {"confirmed": 1.0, "unknown": 0.55, "denied": 0.05},
    "weights": {
        "language": 20,
        "employer": 20,
        "freshness": 20,
        "location": 20,
        "salary": 20,
    },
}


def settings(cfg=None):
    merged = {
        "blue_card_eur": DEFAULTS["blue_card_eur"],
        "factors": dict(DEFAULTS["factors"]),
        "weights": dict(DEFAULTS["weights"]),
    }
    given = (cfg or {}).get("reach") or {}
    if given.get("blue_card_eur") is not None:
        merged["blue_card_eur"] = given["blue_card_eur"]
    merged["factors"].update(given.get("factors") or {})
    merged["weights"].update(given.get("weights") or {})
    return merged


def age_days(posted_at):
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(str(posted_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _fact(key, label, value, points, cap, good):
    return {
        "key": key,
        "label": label,
        "value": value,
        "points": points,
        "max": cap,
        "good": good,
    }


def language_fact(job, prof, cap):
    level = str((prof or {}).get("german_level") or "none").strip().lower()
    speaks_german = level not in WEAK_GERMAN
    if job.get("language_required") == "de" and not speaks_german:
        return _fact("language", "Language needed", "German, which you do not speak", 0, cap, False)
    if job.get("language_required") == "de":
        return _fact("language", "Language needed", "German, which you speak", cap, cap, True)
    return _fact("language", "Language needed", "English is enough", cap, cap, True)


def employer_fact(job, cap):
    if job.get("via_agency"):
        points = int(round(cap * 0.25))
        return _fact("employer", "Who posted it", "a recruitment agency", points, cap, False)
    return _fact("employer", "Who posted it", "the company itself", cap, cap, True)


def freshness_fact(job, cap):
    days = age_days(job.get("posted_at"))
    if days is None:
        return _fact("freshness", "How old the advert is", "not stated", int(round(cap * 0.5)), cap, False)
    if days <= 7:
        return _fact("freshness", "How old the advert is", str(days) + " days", cap, cap, True)
    if days <= 21:
        return _fact("freshness", "How old the advert is", str(days) + " days", int(round(cap * 0.7)), cap, True)
    if days <= 45:
        return _fact("freshness", "How old the advert is", str(days) + " days", int(round(cap * 0.3)), cap, False)
    return _fact("freshness", "How old the advert is", str(days) + " days", 0, cap, False)


def location_fact(job, prof, cap):
    targets = {str(c).upper() for c in ((prof or {}).get("target_countries") or [])}
    country = job.get("country")
    remote = job.get("remote") == "remote"
    if country and country in targets:
        return _fact("location", "Where it is", country + ", a country you target", cap, cap, True)
    if country and country in EUROPEAN:
        return _fact("location", "Where it is", country + ", in Europe but not a target", int(round(cap * 0.5)), cap, True)
    if not country and remote:
        return _fact("location", "Where it is", "remote, country not stated", int(round(cap * 0.8)), cap, True)
    if not country:
        return _fact("location", "Where it is", "not stated", int(round(cap * 0.4)), cap, False)
    return _fact("location", "Where it is", str(country) + ", outside your targets", 0, cap, False)


def salary_fact(job, cap, threshold):
    top = job.get("salary_max") or job.get("salary_min")
    currency = job.get("salary_currency")
    if not top:
        return _fact("salary", "Blue Card salary threshold", "salary not published", int(round(cap * 0.6)), cap, False)
    if currency and currency != "EUR":
        return _fact("salary", "Blue Card salary threshold", str(top) + " " + str(currency) + ", not comparable", int(round(cap * 0.7)), cap, True)
    if top >= threshold:
        return _fact("salary", "Blue Card salary threshold", str(top) + " EUR, clears " + str(threshold), cap, cap, True)
    return _fact("salary", "Blue Card salary threshold", str(top) + " EUR, below " + str(threshold), int(round(cap * 0.3)), cap, False)


def compute(job, cfg=None, prof=None):
    conf = settings(cfg)
    weights = conf["weights"]

    facts = [
        language_fact(job, prof, weights["language"]),
        employer_fact(job, weights["employer"]),
        freshness_fact(job, weights["freshness"]),
        location_fact(job, prof, weights["location"]),
        salary_fact(job, weights["salary"], conf["blue_card_eur"]),
    ]

    earned = sum(f["points"] for f in facts)
    possible = sum(f["max"] for f in facts) or 1
    base = int(round(100.0 * earned / possible))

    status = job.get("sponsorship_status") or "unknown"
    needs = (prof or {}).get("needs_sponsorship", True)
    factor = 1.0 if not needs else float(conf["factors"].get(status, conf["factors"]["unknown"]))

    if not needs:
        sponsor_value = "you do not need sponsorship"
    elif status == "confirmed":
        sponsor_value = "the advert says it sponsors visas"
    elif status == "denied":
        sponsor_value = "the advert rules sponsorship out"
    else:
        sponsor_value = "the advert says nothing about visas"

    facts.insert(0, {
        "key": "sponsorship",
        "label": "Visa sponsorship",
        "value": sponsor_value,
        "points": None,
        "max": None,
        "good": status == "confirmed" or not needs,
        "factor": factor,
    })

    return {
        "reach": max(0, min(100, int(round(base * factor)))),
        "base": base,
        "factor": factor,
        "sponsorship": status,
        "facts": facts,
    }
