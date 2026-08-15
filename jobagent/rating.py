from . import agent, profile

RUBRIC = (
    ("core_technical", 30, "core technical match against his real skills"),
    ("seniority_scope", 20, "seniority and scope against principal architect level"),
    ("domain", 15, "domain overlap with automation, AI and integration work"),
    ("logistics", 20, "location, remote policy and language against what he can do"),
    ("compensation", 10, "compensation, or how promising it looks when unstated"),
    ("signal", 5, "signal, how clearly the advert describes a real matching role"),
)

PROMPT = """You are scoring one job advert against one candidate. Return only JSON.

Score fit out of 100 using exactly this rubric, and put each part in dimensions:
{rubric}

Do NOT return reach. Reachability is computed in Python from facts in the
advert and anything you send for it is discarded. This job already scores
{reach} out of 100 for reach.

{estimates}

Return this shape and nothing else:

{{"fit": 0, "dimensions": {{{dimension_keys}}}, "rationale": "two or three sentences",
  "ats_score": null, "offer_probability": null, "estimate_note": null}}

Be honest and specific in the rationale. Name the single strongest reason it
fits and the single biggest gap. Do not flatter the candidate.

CANDIDATE
{candidate}

JOB
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Employment type: {employment}
Language: {language}
Sponsorship in the advert: {sponsorship}
Salary: {salary}

ADVERT
{description}
"""

ESTIMATES_ON = """This job clears the strong band, so also fill ats_score and
offer_probability as integers from 0 to 100, and set estimate_note to a short
sentence saying they are your estimate rather than a measurement. No applicant
tracking system publishes a score and nothing in an advert predicts an offer."""

ESTIMATES_OFF = """Leave ats_score, offer_probability and estimate_note as null.
This job is below the strong band, so those estimates are not worth the effort."""


def candidate_summary(master, user_profile, bullet_chars=150, max_bullets=18):
    if not master:
        return "No master CV was loaded."
    lines = []
    identity = master.get("identity") or {}
    if identity.get("title"):
        lines.append("Headline: " + str(identity["title"]))
    seniority = (user_profile or {}).get("seniority")
    if seniority:
        lines.append("Seniority: " + str(seniority))
    base = (user_profile or {}).get("base")
    if base:
        lines.append("Based in: " + str(base))
    if (user_profile or {}).get("needs_sponsorship"):
        lines.append("Needs visa sponsorship: yes")
    german = (user_profile or {}).get("german_level")
    if german:
        lines.append("German level: " + str(german))

    tiers = profile.skill_tiers(master)
    labels = {"core": "Strongest", "working": "Has worked with", "familiar": "Some exposure"}
    for tier in ("core", "working", "familiar"):
        entries = tiers.get(tier) or []
        if entries:
            names = ", ".join(
                e["name"] + (" (" + e["context"] + ")" if e.get("context") else "")
                for e in entries
            )
            lines.append(labels[tier] + ": " + names)

    written = 0
    for role in master.get("experience") or []:
        if written >= max_bullets:
            break
        head = " / ".join(
            str(role.get(k)) for k in ("title", "company") if role.get(k)
        )
        if head:
            lines.append("Role: " + head)
        for bullet in role.get("bullets") or []:
            if written >= max_bullets:
                break
            text = bullet.get("text") if isinstance(bullet, dict) else bullet
            if text:
                lines.append("  - " + str(text)[:bullet_chars])
                written += 1
    return "\n".join(lines)


def salary_line(job):
    salary = job.get("salary") or {}
    if not (salary.get("min") or salary.get("max")):
        return "not published"
    return " to ".join(
        str(v) for v in [salary.get("min"), salary.get("max")] if v
    ) + " " + str(salary.get("currency") or "")


def build_prompt(job, master, user_profile, reach, strong):
    rubric = "\n".join(
        "- " + key + ", up to " + str(cap) + ": " + note for key, cap, note in RUBRIC
    )
    keys = ", ".join('"' + key + '": 0' for key, _, _ in RUBRIC)
    return PROMPT.format(
        rubric=rubric,
        reach=reach,
        estimates=ESTIMATES_ON if strong else ESTIMATES_OFF,
        dimension_keys=keys,
        candidate=candidate_summary(master, user_profile),
        title=job.get("title") or "not stated",
        company=job.get("company") or "not stated",
        location=", ".join(
            str(x) for x in [job.get("city"), job.get("country")] if x
        ) or "not stated",
        remote=job.get("remote") or "not stated",
        employment=job.get("employment_type") or "not stated",
        language=job.get("language") or "not stated",
        sponsorship=job.get("sponsorship") or "unknown",
        salary=salary_line(job),
        description=(job.get("description") or "").strip() or "no advert text stored",
    )


def _int(value, low=0, high=100):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(low, min(high, number))


def clean(data, strong):
    dimensions = {}
    given = data.get("dimensions")
    if isinstance(given, dict):
        for key, cap, _ in RUBRIC:
            value = _int(given.get(key), 0, cap)
            if value is not None:
                dimensions[key] = value

    if len(dimensions) == len(RUBRIC):
        fit = sum(dimensions.values())
    else:
        fit = _int(data.get("fit"))
    if fit is None:
        raise agent.AgentError("Claude did not return a usable fit score.")

    rationale = data.get("rationale")
    rationale = str(rationale).strip() if rationale else None

    ats = _int(data.get("ats_score")) if strong else None
    offer = _int(data.get("offer_probability")) if strong else None
    note = data.get("estimate_note") if strong else None
    if (ats is not None or offer is not None) and not note:
        note = "Both numbers are an estimate, not a measurement."

    return {
        "fit": fit,
        "dimensions": dimensions or None,
        "rationale": rationale,
        "ats_score": ats,
        "offer_probability": offer,
        "estimate_note": str(note).strip() if note else None,
    }


def score(job, master, user_profile, reach, limits, timeout=agent.DEFAULT_TIMEOUT,
          provider=agent.DEFAULT_PROVIDER):
    strong_reach = reach >= limits["strong_chance"]
    prompt = build_prompt(job, master, user_profile, reach, strong_reach)
    data = agent.run_json(prompt, timeout, provider)
    result = clean(data, strong_reach)
    if result["fit"] < limits["strong_match"]:
        result["ats_score"] = None
        result["offer_probability"] = None
        result["estimate_note"] = None
    return result


ESTIMATE_KINDS = {
    "ats": (
        "cv score",
        "Guess how a resume-screening system (an ATS) would score this candidate's "
        "CV against this job advert, as an integer from 0 to 100. No real ATS "
        "publishes a score like this, so be clear in your note that it is an estimate "
        "based on keyword and requirement overlap, not a measurement.",
    ),
    "offer": (
        "offer guess",
        "Guess the probability, as an integer from 0 to 100, that applying to this "
        "job leads to an offer. Nothing can truly predict this, so give an honest, "
        "calibrated guess using the fit and reach numbers below, and say in your "
        "note that it is a guess, not a prediction.",
    ),
}

ESTIMATE_PROMPT = """You already scored this job. Now give ONE more number on demand,
requested directly rather than as part of the normal flow.

Fit already scored: {fit} out of 100. Reach (computed, not yours to change): {reach}
out of 100. Your earlier reasoning: {rationale}

{question}

Return only JSON: {{"value": 0, "note": "one short sentence"}}

CANDIDATE
{candidate}

JOB
Title: {title}
Company: {company}
Location: {location}

ADVERT
{description}
"""


def build_estimate_prompt(job, master, user_profile, fit, rationale, reach, kind):
    _, question = ESTIMATE_KINDS[kind]
    return ESTIMATE_PROMPT.format(
        fit=fit,
        reach=reach,
        rationale=rationale or "not recorded",
        question=question,
        candidate=candidate_summary(master, user_profile),
        title=job.get("title") or "not stated",
        company=job.get("company") or "not stated",
        location=", ".join(
            str(x) for x in [job.get("city"), job.get("country")] if x
        ) or "not stated",
        description=(job.get("description") or "").strip() or "no advert text stored",
    )


def clean_estimate(data):
    value = _int(data.get("value"))
    if value is None:
        raise agent.AgentError("Claude did not return a usable number.")
    note = data.get("note")
    note = str(note).strip() if note else "This is an estimate, not a measurement."
    return {"value": value, "note": note}


def estimate(job, master, user_profile, fit, rationale, reach, kind,
             timeout=agent.DEFAULT_TIMEOUT, provider=agent.DEFAULT_PROVIDER):
    if kind not in ESTIMATE_KINDS:
        raise ValueError("kind must be one of " + ", ".join(ESTIMATE_KINDS))
    prompt = build_estimate_prompt(job, master, user_profile, fit, rationale, reach, kind)
    data = agent.run_json(prompt, timeout, provider)
    return clean_estimate(data)
