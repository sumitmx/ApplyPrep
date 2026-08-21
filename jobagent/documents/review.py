from .. import agent

REVIEW_PROMPT = """You are reviewing an already-tailored CV against one specific job
posting. Return only a JSON object, no prose, no code fence.

Give an honest, specific review from a hiring manager's point of view. Strengths and
improvements must describe what is actually on the CV below - diagnostic only, do
not invent facts. Suggestions may go further: name something the candidate could add
that is not yet on the CV, because the candidate reviews and edits every suggestion
before anything is added. Suggestions must not contradict facts already on the CV
(employers, dates, numbers, job titles) - only add, never alter what is stated.

Shape:
{"strengths": ["<specific strength, one clause>", ...],
"improvements": ["<specific gap or weakness, one clause>", ...],
"suggestions": [{"text": "<a bullet the candidate could add, ready to use as written>",
"why": "<one short clause on why it would help for this job>"}]}

Give 3 to 6 strengths, 3 to 6 improvements, and up to 5 suggestions.

THE JOB
Title: {title}
Company: {company}
Location: {location}

{description}

THE TAILORED CV
{cv_text}
"""


def _fill(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def review_cv(job, cv_text, timeout=agent.DEFAULT_TIMEOUT, provider=agent.DEFAULT_PROVIDER):
    cv_text = (cv_text or "").strip()
    if not cv_text:
        raise agent.AgentError("Write a CV for this job first.")
    prompt = _fill(REVIEW_PROMPT, {
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location": ", ".join(x for x in [job.get("city"), job.get("country")] if x),
        "description": (job.get("description") or "")[:6000],
        "cv_text": cv_text,
    })
    data = agent.run_json(prompt, timeout, provider)

    strengths = [str(s).strip() for s in (data.get("strengths") or []) if str(s).strip()]
    improvements = [
        str(s).strip() for s in (data.get("improvements") or []) if str(s).strip()
    ]

    suggestions = []
    for item in data.get("suggestions") or []:
        text = str((item or {}).get("text") or "").strip()
        if not text:
            continue
        why = str((item or {}).get("why") or "").strip()
        suggestions.append({"text": text, "why": why or None})

    return {
        "strengths": strengths,
        "improvements": improvements,
        "suggestions": suggestions,
    }
