import re
from datetime import datetime, timezone

from . import profile

_PATTERNS = {}

_SEPARATOR = r"[\s\-/_.]+"


def _pattern(term):
    cached = _PATTERNS.get(term)
    if cached is None:
        words = [re.escape(w) for w in term.lower().split() if w]
        if not words:
            return None
        body = _SEPARATOR.join(words)
        cached = re.compile(r"(?<!\w)" + body + r"(?!\w)")
        _PATTERNS[term] = cached
    return cached


def first_match(text, terms):
    low = (text or "").lower()
    for term in terms or []:
        pattern = _pattern(term)
        if pattern and pattern.search(low):
            return term
    return None


def age_days(posted_at):
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


# ── seniority ──────────────────────────────────────────────────────────────
# The boards hand over everything recent, and a title rarely says what level a
# role is: "Software Engineer" is used for a first job and for a fifteen-year
# one. The requirement almost always sits in the description instead, so that
# is where this looks.

# A number followed by a years unit. A range - "3-5 years", "3 bis 5 Jahre" -
# contributes its lower bound, since that is the actual requirement.
_YEARS_RE = re.compile(
    r"(?<![\w.,])(\d{1,2})\s*"
    r"(?:\+|plus)?\s*"
    r"(?:(?:-|–|—|to|bis)\s*\d{1,2}\s*\+?\s*)?"
    r"\+?\s*"
    r"(?:years?|yrs?|jahren?|jahr)(?!\w)",
    re.IGNORECASE,
)

# A bare "10 years" could be anything - how long the company has existed, how
# long the product has shipped. It only counts as a requirement when one of
# these sits near it, so a year count with no experience framing is ignored.
_EXPERIENCE_CONTEXT = re.compile(
    r"experien|erfahrung|praxis|hands[\s\-]?on|background|track record"
    r"|seniorit|at least|minimum|mindestens|min\.",
    re.IGNORECASE,
)

_CONTEXT_WINDOW = 90


def years_required(text):
    """The most years of experience a posting asks for, or None if it never says.

    Every stated requirement is collected and the largest wins: a posting
    wanting "8+ years overall, 2+ years with Kubernetes" is an eight-year role,
    not a two-year one. Nothing is inferred - a posting that never states a
    number returns None and is left for the other checks to judge.
    """
    if not text:
        return None
    best = None
    for match in _YEARS_RE.finditer(text):
        window = text[max(0, match.start() - _CONTEXT_WINDOW):match.end() + _CONTEXT_WINDOW]
        if not _EXPERIENCE_CONTEXT.search(window):
            continue
        years = int(match.group(1))
        if years > 40:
            continue
        if best is None or years > best:
            best = years
    return best


def _skill_overlap_count(job, master):
    tiers = profile.match_skills(master, job.get("title", "") + "\n" + (job.get("description") or ""))
    return len(tiers.get("core") or []) + len(tiers.get("working") or [])


def evaluate(job, gate_cfg, master=None):
    title = job.get("title") or ""
    sponsorship = job.get("sponsorship_status")

    bad = first_match(title, gate_cfg.get("title_must_not_match", []))
    if bad:
        return "rejected", "title contains " + bad

    if sponsorship == "denied":
        return "rejected", "sponsorship explicitly denied"

    sponsors = sponsorship == "confirmed"
    bypass = sponsors and gate_cfg.get("sponsor_bypass_title", True)

    includes = gate_cfg.get("title_must_match", [])
    matched = first_match(title, includes) if includes else None
    if includes and not matched and not bypass:
        return "rejected", "title matched no target keyword"

    generic = gate_cfg.get("title_generic_keywords", [])
    weak_signal = (bypass and not matched) or (matched and matched in generic)
    if weak_signal and master:
        needed = gate_cfg.get("skill_overlap_min", 2)
        if _skill_overlap_count(job, master) < needed:
            if bypass and not matched:
                return "rejected", "sponsors visas, but title and skills did not match your profile"
            return "rejected", "title matched " + str(matched) + " but not enough matching skills"

    # Seniority, from the description. Only an explicit number can reject: a
    # posting that never states one is left alone rather than guessed at.
    floor = gate_cfg.get("min_years_experience")
    if floor:
        wanted = years_required(job.get("description"))
        if wanted is not None and wanted < floor:
            unit = " year" if wanted == 1 else " years"
            return "rejected", "asks for only " + str(wanted) + unit + " of experience"

    max_age = gate_cfg.get("max_age_days")
    age = age_days(job.get("posted_at"))
    if max_age is not None and age is not None and age > max_age:
        return "rejected", "stale, " + str(age) + " days old"

    if not gate_cfg.get("allow_contract", True):
        if first_match(job.get("employment_type"), ["contract", "freelance"]):
            return "rejected", "contract role"

    floor = gate_cfg.get("min_salary_eur")
    if floor is not None and job.get("salary_max") and job.get("salary_currency") == "EUR":
        if job["salary_max"] < floor:
            return "rejected", "salary ceiling below floor"

    if gate_cfg.get("require_english_only") and job.get("language_required") == "de":
        return "rejected", "german required"

    if bypass and not matched:
        return "passed", "kept because it sponsors visas, title did not match"
    return "passed", None
