import re

from . import agent

MAX_HISTORY_TURNS = 16
MAX_DESCRIPTION_CHARS = 16000

SYSTEM = """You are helping a candidate think through ONE specific job posting inside
their personal job-tracking app, ApplyPrep. Answer only about this job, using the facts
below. Be direct and concise, like a sharp friend, not a corporate assistant. Plain text,
no markdown headers or bullet walls unless a list genuinely helps.

Some fields below (the badges, the sponsorship label, the band, "requirements") are
generated automatically by simple keyword rules and can be wrong. A common failure: a
sentence like "we are unable to offer visa sponsorship" gets misread as confirming
sponsorship, because it contains the words "visa sponsorship". Always trust the raw
ADVERT TEXT at the bottom over the app's own labels above it. If the candidate asks about
a badge or label, or you notice one contradicts the advert text, say so plainly and
explain the mismatch - do not paper over it.

If something is not stated in the advert or the facts below, say it is not stated.
Do not invent details.

JOB FACTS
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Employment type: {employment}
Language required: {language}
Salary: {salary}
Posted: {posted_age}
Via agency: {via_agency}
App's sponsorship label: {sponsorship}
App's badges: {badges}
Gate status: {gate_status}{gate_reason}
Match score (fit, out of 100): {fit}
Reach, chance of landing it (out of 100): {reach}
{rationale_line}{dimensions_line}
ADVERT TEXT (the actual posting - this is the ground truth)
{description}
"""


def _salary_line(job):
    salary = job.get("salary") or {}
    if not (salary.get("min") or salary.get("max")):
        return "not published"
    return " to ".join(
        str(v) for v in [salary.get("min"), salary.get("max")] if v
    ) + " " + str(salary.get("currency") or "")


def _facts(job):
    scores = job.get("scores") or {}
    badges = job.get("badges") or []
    gate_reason = job.get("gate_reason")
    rationale = job.get("rationale")
    dimensions = job.get("dimensions")
    return SYSTEM.format(
        title=job.get("title") or "not stated",
        company=job.get("company") or "not stated",
        location=", ".join(
            str(x) for x in [job.get("city"), job.get("country")] if x
        ) or "not stated",
        remote=job.get("remote") or "not stated",
        employment=job.get("employment_type") or "not stated",
        language=job.get("language") or "not stated",
        salary=_salary_line(job),
        posted_age=job.get("posted_age") or "not stated",
        via_agency="yes" if job.get("via_agency") else "no",
        sponsorship=job.get("sponsorship") or "unknown",
        badges=", ".join(b["text"] for b in badges) if badges else "none",
        gate_status=job.get("gate_status") or "not stated",
        gate_reason=(" (" + gate_reason + ")") if gate_reason else "",
        fit="not rated yet" if scores.get("fit") is None else scores["fit"],
        reach="not worked out yet" if scores.get("reach") is None else scores["reach"],
        rationale_line=("Why it was rated this way: " + rationale + "\n") if rationale else "",
        dimensions_line=("Score breakdown: " + str(dimensions) + "\n") if dimensions else "",
        description=(job.get("description") or "no advert text stored")[:MAX_DESCRIPTION_CHARS],
    )


def build_prompt(job, history, question):
    parts = [_facts(job), "CONVERSATION SO FAR"]
    turns = (history or [])[-MAX_HISTORY_TURNS:]
    if not turns:
        parts.append("(nothing yet)")
    else:
        for turn in turns:
            speaker = "Candidate" if turn.get("role") == "user" else "You"
            parts.append(speaker + ": " + str(turn.get("content") or "").strip())
    parts.append("Candidate: " + question.strip())
    parts.append(
        "Write only your reply to the candidate, as plain prose with no speaker "
        'label (do not prefix it with "You:" or similar). A few sentences is '
        "usually enough; only go longer if the question genuinely needs it."
    )
    return "\n\n".join(parts)


_SPEAKER_PREFIX = re.compile(r"^(you|assistant|ai|claude|chatgpt)\s*:\s*", re.IGNORECASE)


def ask(job, history, question, timeout=agent.DEFAULT_TIMEOUT,
        provider=agent.DEFAULT_PROVIDER):
    prompt = build_prompt(job, history, question)
    answer = agent.run(prompt, timeout, provider).strip()
    return _SPEAKER_PREFIX.sub("", answer, count=1).strip()
