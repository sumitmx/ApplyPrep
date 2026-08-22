import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import agent
from . import chat as chat_module
from . import dedup as dedup_module
from . import documents as documents_module
from . import gmail_match, gmail_sync, profile, rating, skills as skills_module, store
from .gmail import auth as gmail_auth
from .documents import palette, pdf, render, tailor
from .documents.guard import known_bullets

MARK_ACTIONS = {
    "shortlist": "shortlisted",
    "hide": "hidden",
    "reject": "rejected",
    "reset": "new",
}

FUNNEL = ("drafting", "applied", "screening", "interview", "offer", "rejected")

RESPONDED = ("screening", "interview", "offer", "rejected")

LATEST_SCORE = (
    " LEFT JOIN (SELECT job_id, MAX(scored_at) AS scored_at FROM score GROUP BY job_id)"
    " newest ON newest.job_id = job.id"
    " LEFT JOIN score ON score.job_id = job.id AND score.scored_at = newest.scored_at"
    " LEFT JOIN job_reach ON job_reach.job_id = job.id"
)

EFFECTIVE_REACH = "COALESCE(job_reach.reach, score.reach)"

JOB_FIELDS = (
    "job.id, job.title, job.company_name, job.country, job.city, job.remote,"
    " job.employment_type, job.posted_at, job.url, job.description,"
    " job.salary_min, job.salary_max, job.salary_currency, job.sponsorship_status,"
    " job.language_required, job.via_agency, job.gate_status, job.gate_reason,"
    " job.status, job.first_seen_at, job.last_seen_at, job.source_ids,"
    " score.fit, score.reach, score.ats_score, score.offer_probability,"
    " score.dimensions, score.rationale, score.model, score.scored_at,"
    " score.estimate_note,"
    " job_reach.reach AS computed_reach, job_reach.base AS reach_base,"
    " job_reach.factor AS reach_factor"
)

def _source_names(conn):
    return {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM source")}


def websites_for(source_ids_json, names):
    ids = _json(source_ids_json) or []
    return [names[i] for i in ids if i in names]


def now():
    return datetime.now(timezone.utc)


def _parse(stamp):
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def age_hours(stamp):
    dt = _parse(stamp)
    if dt is None:
        return None
    return (now() - dt).total_seconds() / 3600.0


def relative_age(stamp):
    hours = age_hours(stamp)
    if hours is None:
        return None
    if hours < 1:
        return "just now"
    if hours < 24:
        count = int(hours)
        return str(count) + (" hour ago" if count == 1 else " hours ago")
    days = int(hours // 24)
    if days < 30:
        return str(days) + (" day ago" if days == 1 else " days ago")
    months = days // 30
    return str(months) + (" month ago" if months == 1 else " months ago")


def badges(row):
    out = []
    sponsorship = row.get("sponsorship_status")
    if sponsorship == "confirmed":
        out.append({"text": "sponsors visas", "tone": "pine", "strong": True})
    elif sponsorship == "denied":
        out.append({"text": "no visa sponsorship", "tone": "rust", "strong": True})
    else:
        out.append({"text": "visa not mentioned", "tone": "rust", "strong": True})
    if row.get("language_required") == "de":
        out.append({"text": "German needed", "tone": "amber", "strong": True})
    else:
        out.append({"text": "English is enough", "tone": "pine"})
    if row.get("via_agency"):
        out.append({"text": "posted by an agency", "tone": "rust"})
    else:
        out.append({"text": "posted by the company", "tone": "pine"})
    if row.get("remote") == "remote":
        out.append({"text": "remote", "tone": "pine"})
    hours = age_hours(row.get("posted_at"))
    if hours is not None and hours > 24 * 30:
        out.append({"text": str(int(hours // 24)) + " days old", "tone": "rust"})
    return out


BANDS = [
    {"key": "strong", "label": "Best bets", "tone": "pine",
     "blurb": "Suit you well and realistically reachable"},
    {"key": "medium", "label": "Worth considering", "tone": "mint",
     "blurb": "A decent fit, or reachable but not an obvious match"},
    {"key": "unrated", "label": "Not rated yet", "tone": "amber",
     "blurb": "Ask Claude to rate these and they move into a band"},
    {"key": "low", "label": "Long shots", "tone": "rust",
     "blurb": "Weak on merit, on reachability, or both"},
]

DEFAULT_BANDS = {
    "strong_match": 70,
    "strong_chance": 50,
    "medium_match": 45,
    "medium_chance": 45,
}

BAND_RANK = {"strong": 0, "medium": 1, "unrated": 2, "low": 3}
RANK_BAND = {v: k for k, v in BAND_RANK.items()}


def band_limits(cfg=None):
    return dict(DEFAULT_BANDS, **((cfg or {}).get("bands") or {}))


AI_PROVIDER_KEY = "ai_provider"


def get_ai_provider(conn):
    return store.get_setting(conn, AI_PROVIDER_KEY, agent.DEFAULT_PROVIDER)


def set_ai_provider(conn, provider):
    if provider not in agent.PROVIDERS:
        raise ValueError("unknown AI provider " + repr(provider))
    store.set_setting(conn, AI_PROVIDER_KEY, provider)
    return provider


def ai_providers(conn):
    return {
        "current": get_ai_provider(conn),
        "options": [
            {
                "key": key,
                "label": info["label"],
                "available": agent.available(key),
                "model": agent.model(key),
            }
            for key, info in agent.PROVIDERS.items()
        ],
    }


def band_for(fit, reach, limits=None, gate_status=None):
    limits = limits or DEFAULT_BANDS
    if gate_status == "rejected":
        return "low"
    if fit is None:
        return "unrated"
    chance = reach if reach is not None else 0
    if fit >= limits["strong_match"] and chance >= limits["strong_chance"]:
        return "strong"
    if fit >= limits["medium_match"] or chance >= limits["medium_chance"]:
        return "medium"
    return "low"


_HEADING_MAX = 80

_REQUIREMENTS_START = re.compile(
    r"requirements?\b|\brequired\b|qualifications?|who you are\b|about you\b|"
    r"your profile\b|what you.{0,4}(ll bring|bring|need)|what we.{0,4}re looking for|"
    r"you (have|bring)\b|must haves?\b|technical (requirements?|skills)|skills?\b|"
    r"nice to have|preferred qualification",
    re.I,
)

_REQUIREMENTS_STOP = re.compile(
    r"responsibilit|what you.{0,4}ll do|about (the|us|our)\b|who we are\b|\bthe role\b|"
    r"your (team|day one|impact)\b|benefit|perk|compensation|salary range|"
    r"equal opportunit|how to apply|why (join|choose|us)\b|our (mission|values|culture)|"
    r"diversit|apply now|next steps|company overview|what we offer|life at |"
    r"interview process|hiring process",
    re.I,
)


def _is_heading_line(line):
    text = line.strip()
    if not text or len(text) > _HEADING_MAX or text.startswith("-"):
        return False
    return text[-1] not in ".!?,;"


def requirements_section(description):
    lines = str(description or "").split("\n")
    start = None
    for i, line in enumerate(lines):
        if _is_heading_line(line) and _REQUIREMENTS_START.search(line.strip()):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _is_heading_line(lines[i]) and _REQUIREMENTS_STOP.search(lines[i].strip()):
            end = i
            break
    kept = [line for line in lines[start:end] if line.strip() != "-"]
    section = "\n".join(kept).strip()
    return section or None


def shape_job(row, limits=None, source_names=None):
    data = dict(row)
    scored = data.get("scored_at") is not None
    requirements = requirements_section(data.get("description"))
    job = {
        "id": data["id"],
        "title": data.get("title"),
        "company": data.get("company_name"),
        "country": data.get("country"),
        "city": data.get("city"),
        "remote": data.get("remote"),
        "employment_type": data.get("employment_type"),
        "posted_at": data.get("posted_at"),
        "posted_age": relative_age(data.get("posted_at")),
        "found_age": relative_age(data.get("first_seen_at")),
        "url": data.get("url"),
        "websites": websites_for(data.get("source_ids"), source_names or {}),
        "sponsorship": data.get("sponsorship_status"),
        "language": data.get("language_required"),
        "via_agency": bool(data.get("via_agency")),
        "gate_status": data.get("gate_status"),
        "gate_reason": data.get("gate_reason"),
        "status": data.get("status"),
        "saved": data.get("status") == "shortlisted",
        "applied": data.get("application_applied_at") is not None,
        "requirements": requirements or (data.get("description") or "").strip() or None,
        "requirements_found": requirements is not None,
        "badges": badges(data),
        "scored": scored,
        "salary": {
            "min": data.get("salary_min"),
            "max": data.get("salary_max"),
            "currency": data.get("salary_currency"),
        },
    }
    computed = data.get("computed_reach")
    reach = computed if computed is not None else data.get("reach")
    job["scores"] = {
        "fit": data.get("fit"),
        "reach": reach,
        "reach_source": "computed" if computed is not None else (
            "model" if data.get("reach") is not None else None
        ),
        "reach_base": data.get("reach_base"),
        "reach_factor": data.get("reach_factor"),
        "ats_score": data.get("ats_score"),
        "offer_probability": data.get("offer_probability"),
        "model": data.get("model"),
        "scored_at": data.get("scored_at"),
        "note": data.get("estimate_note"),
        "estimated": ["ats_score", "offer_probability"],
    }
    job["band"] = band_for(data.get("fit"), reach, limits, data.get("gate_status"))
    return job


BAND_RANK_SQL = (
    "CASE"
    " WHEN job.gate_status = 'rejected' THEN 3"
    " WHEN score.fit IS NULL THEN 2"
    " WHEN score.fit >= ? AND " + EFFECTIVE_REACH + " >= ? THEN 0"
    " WHEN score.fit >= ? OR " + EFFECTIVE_REACH + " >= ? THEN 1"
    " ELSE 3"
    " END"
)


def jobs(conn, gate=None, country=None, min_fit=None, status=None,
         hours=None, remote=None, agency=None, source=None, band=None,
         applied=None, draft_cv=None, limit=50, offset=0, limits=None):
    limits = limits or DEFAULT_BANDS
    band_args = [
        limits["strong_match"], limits["strong_chance"],
        limits["medium_match"], limits["medium_chance"],
    ]
    joins = LATEST_SCORE + " LEFT JOIN application ON application.job_id = job.id"
    where = []
    args = []
    if gate:
        where.append("job.gate_status = ?")
        args.append(gate)
    if country:
        where.append("job.country = ?")
        args.append(country)
    if remote:
        where.append("job.remote = ?")
        args.append(remote)
    if agency is not None:
        where.append("job.via_agency = ?")
        args.append(1 if agency else 0)
    if status:
        where.append("job.status = ?")
        args.append(status)
    else:
        where.append("job.status NOT IN ('hidden', 'rejected')")
    if min_fit is not None:
        where.append("score.fit >= ?")
        args.append(min_fit)
    if hours is not None:
        cutoff = (now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        where.append("job.posted_at >= ?")
        args.append(cutoff)
    if source:
        where.append(
            "job.id IN (SELECT jj.id FROM job AS jj, json_each(jj.source_ids) je"
            " WHERE je.value = (SELECT id FROM source WHERE name = ?))"
        )
        args.append(source)
    if band:
        where.append("(" + BAND_RANK_SQL + ") = ?")
        args.extend(band_args)
        args.append(BAND_RANK.get(band, -1))
    if applied:
        where.append("application.applied_at IS NOT NULL")
    else:
        where.append("application.applied_at IS NULL")
    if draft_cv:
        where.append(
            "job.id IN (SELECT job_id FROM document"
            " WHERE kind = 'cv' AND accepted = 0)"
        )
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        "SELECT COUNT(*) AS n FROM job" + joins + clause, args
    ).fetchone()["n"]

    rows = conn.execute(
        "SELECT " + JOB_FIELDS + ", application.applied_at AS application_applied_at"
        " FROM job" + joins + clause +
        " ORDER BY " + BAND_RANK_SQL + " ASC, " + EFFECTIVE_REACH +
        " DESC, score.fit DESC, job.posted_at DESC"
        " LIMIT ? OFFSET ?",
        args + band_args + [limit, offset],
    ).fetchall()
    names = _source_names(conn)
    shaped = [shape_job(r, limits, names) for r in rows]
    counts = {}
    for job in shaped:
        counts[job["band"]] = counts.get(job["band"], 0) + 1
    total_passed = conn.execute(
        "SELECT COUNT(*) AS n FROM job LEFT JOIN application"
        " ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed'"
        " AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
    ).fetchone()["n"]
    return {"total": total, "total_passed": total_passed, "limit": limit,
            "offset": offset, "jobs": shaped, "bands": BANDS, "band_counts": counts}


def job_detail(conn, job_id, master=None):
    row = conn.execute(
        "SELECT " + JOB_FIELDS + " FROM job" + LATEST_SCORE + " WHERE job.id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    job = shape_job(row, source_names=_source_names(conn))
    job["description"] = row["description"]
    job["dimensions"] = _json(row["dimensions"])
    job["rationale"] = row["rationale"]
    job["skill_match"] = profile.match_skills(master, row["description"]) if master else None
    job["documents"] = documents(conn, job_id)
    stored = store.get_reach(conn, job_id)
    job["reach_facts"] = _json(stored["facts"]) if stored else None
    app_row = conn.execute(
        "SELECT id, status, applied_at FROM application WHERE job_id = ?", (job_id,)
    ).fetchone()
    job["application"] = dict(app_row) if app_row else None
    job["applied"] = bool(app_row and app_row["applied_at"])
    return job


def _json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def neighbours(conn, job_id, gate="passed"):
    ids = [r["id"] for r in conn.execute(
        "SELECT job.id FROM job" + LATEST_SCORE +
        " WHERE job.gate_status = ? ORDER BY score.fit DESC, job.posted_at DESC",
        (gate,),
    ).fetchall()]
    if job_id not in ids:
        return {"previous": None, "next": None}
    i = ids.index(job_id)
    return {
        "previous": ids[i - 1] if i > 0 else None,
        "next": ids[i + 1] if i < len(ids) - 1 else None,
    }


def mark_job(conn, job_id, action, reason=None):
    if action not in MARK_ACTIONS:
        raise ValueError("unknown action " + str(action))
    new_status = MARK_ACTIONS[action]
    cur = conn.execute(
        "UPDATE job SET status = ? WHERE id = ?", (new_status, job_id)
    )
    if reason:
        conn.execute(
            "UPDATE job SET gate_reason = ? WHERE id = ?", (reason, job_id)
        )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return {"id": job_id, "status": new_status, "reason": reason}


def pending_jobs(conn, limit=50):
    rows = conn.execute(
        "SELECT " + JOB_FIELDS + " FROM job" + LATEST_SCORE +
        " WHERE job.gate_status = 'passed' AND job.status NOT IN ('hidden', 'rejected')"
        " AND score.fit IS NULL"
        " ORDER BY CASE job.sponsorship_status"
        "   WHEN 'confirmed' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END,"
        " " + EFFECTIVE_REACH + " DESC,"
        " job.via_agency, job.posted_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [shape_job(r) for r in rows]


def pending_count(conn):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM job WHERE gate_status = 'passed'"
        " AND status NOT IN ('hidden', 'rejected')"
        " AND id NOT IN (SELECT job_id FROM score)"
    ).fetchone()["n"]


def job_brief(conn, job_id, master=None, description_chars=4000):
    job = job_detail(conn, job_id, master)
    if job is None:
        return None
    text = job.get("description") or ""
    job["description"] = text[:description_chars]
    job["description_truncated"] = len(text) > description_chars
    return job


def save_score(conn, job_id, fit, reach=None, dimensions=None, rationale=None,
               ats_score=None, offer_probability=None, model=None,
               estimate_note=None, profile_version="v1", rubric_version="v1"):
    exists = conn.execute("SELECT 1 FROM job WHERE id = ?", (job_id,)).fetchone()
    if not exists:
        return None
    if reach is None:
        stored = store.get_reach(conn, job_id)
        reach = stored["reach"] if stored else 0
    for name, value in (("fit", fit), ("reach", reach),
                        ("ats_score", ats_score),
                        ("offer_probability", offer_probability)):
        if value is not None and not 0 <= value <= 100:
            raise ValueError(name + " must be between 0 and 100, got " + str(value))
    store.upsert_score(conn, {
        "job_id": job_id,
        "fit": fit,
        "reach": reach,
        "dimensions": dimensions,
        "rationale": rationale,
        "ats_score": ats_score,
        "offer_probability": offer_probability,
        "model": model,
        "estimate_note": estimate_note,
        "profile_version": profile_version,
        "rubric_version": rubric_version,
    })
    return {"job_id": job_id, "fit": fit, "reach": reach}


def save_scores(conn, batch, model=None):
    saved = []
    missing = []
    for item in batch:
        result = save_score(
            conn,
            item["job_id"],
            item["fit"],
            item.get("reach"),
            dimensions=item.get("dimensions"),
            rationale=item.get("rationale"),
            ats_score=item.get("ats_score"),
            offer_probability=item.get("offer_probability"),
            estimate_note=item.get("estimate_note"),
            model=item.get("model", model),
        )
        if result is None:
            missing.append(item["job_id"])
        else:
            saved.append(result)
    return {"saved": saved, "unknown_job_ids": missing}


def mark_many(conn, marks):
    done = []
    missing = []
    for item in marks:
        result = mark_job(conn, item["job_id"], item["action"], item.get("reason"))
        if result is None:
            missing.append(item["job_id"])
        else:
            done.append(result)
    return {"marked": done, "unknown_job_ids": missing}


def top_jobs(conn, limit=10, min_fit=None):
    where = "WHERE job.gate_status = 'passed' AND score.fit IS NOT NULL"
    args = []
    if min_fit is not None:
        where += " AND score.fit >= ?"
        args.append(min_fit)
    rows = conn.execute(
        "SELECT " + JOB_FIELDS + " FROM job" + LATEST_SCORE + " " + where +
        " ORDER BY score.fit DESC, " + EFFECTIVE_REACH + " DESC LIMIT ?",
        args + [limit],
    ).fetchall()
    return [shape_job(r) for r in rows]


def dashboard(conn, hours=168, limits=None):
    limits = limits or DEFAULT_BANDS
    counts = {}
    for row in conn.execute(
        "SELECT gate_status, COUNT(*) AS n FROM job GROUP BY gate_status"
    ):
        counts[row["gate_status"]] = row["n"]

    band_args = [
        limits["strong_match"], limits["strong_chance"],
        limits["medium_match"], limits["medium_chance"],
    ]
    band_counts = {b["key"]: 0 for b in BANDS}
    for row in conn.execute(
        "SELECT (" + BAND_RANK_SQL + ") AS rank, COUNT(*) AS n"
        " FROM job" + LATEST_SCORE +
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed' AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY rank",
        band_args,
    ):
        band_counts[RANK_BAND.get(row["rank"], "low")] = row["n"]

    cutoff = (now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    window_counts = {}
    for row in conn.execute(
        "SELECT job.gate_status AS gate_status, COUNT(*) AS n FROM job"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.posted_at >= ? AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY job.gate_status",
        (cutoff,),
    ):
        window_counts[row["gate_status"]] = row["n"]
    window_total = sum(window_counts.values())

    all_awaiting = conn.execute(
        "SELECT COUNT(*) AS n FROM job LEFT JOIN application"
        " ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed'"
        " AND job.status NOT IN ('hidden', 'rejected')"
        " AND job.id NOT IN (SELECT job_id FROM score)"
        " AND application.applied_at IS NULL"
    ).fetchone()["n"]

    all_passed = conn.execute(
        "SELECT COUNT(*) AS n FROM job LEFT JOIN application"
        " ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed'"
        " AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
    ).fetchone()["n"]

    shortlisted = conn.execute(
        "SELECT COUNT(*) AS n FROM job WHERE status = 'shortlisted'"
    ).fetchone()["n"]

    month = now().strftime("%Y-%m")
    applied_month = conn.execute(
        "SELECT COUNT(*) AS n FROM application WHERE applied_at LIKE ?",
        (month + "%",),
    ).fetchone()["n"]

    drafted_not_saved = conn.execute(
        "SELECT COUNT(*) AS n FROM document"
        " JOIN job ON job.id = document.job_id"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE document.kind = 'cv' AND document.accepted = 0"
        " AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
    ).fetchone()["n"]

    last_run = conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 1").fetchone()
    period = _period_label(hours)

    return {
        "window_hours": hours,
        "last_run": dict(last_run) if last_run else None,
        "cards": [
            {"key": "New postings", "value": window_total, "tone": None,
             "sub": ("posted in the last " + period) if window_total
             else "nothing posted in the last " + period},
            {"key": "Worth a look", "value": all_passed, "tone": "mint",
             "sub": "in Jobs right now" if all_passed else "nothing worth a look yet"},
            {"key": "Not rated yet", "value": all_awaiting, "tone": "amber",
             "sub": "ask Claude to rate these" if all_awaiting
             else "all caught up"},
            {"key": "You saved", "value": shortlisted, "tone": "pine",
             "sub": "your shortlist, all time"},
            {"key": "Applied this month", "value": applied_month, "tone": None,
             "sub": now().strftime("%B %Y")},
            {"key": "CV drafted, not saved", "value": drafted_not_saved, "tone": "amber",
             "sub": "Write my CV was clicked, never downloaded" if drafted_not_saved
             else "nothing waiting"},
        ],
        "response_by_band": response_by_band(conn),
        "next_actions": next_actions(conn, all_awaiting),
        "gate_counts": counts,
        "band_counts": band_counts,
        "bands": BANDS,
    }


def _period_label(hours):
    if hours % 24 == 0:
        days = hours // 24
        return str(days) + (" day" if days == 1 else " days")
    return str(hours) + (" hour" if hours == 1 else " hours")


def response_by_band(conn):
    bands = [("Strong matches, 80 and up", 80, 100), ("Decent matches, 60 to 79", 60, 79)]
    out = []
    for label, low, high in bands:
        rows = conn.execute(
            "SELECT application.status FROM application"
            " JOIN job ON job.id = application.job_id" + LATEST_SCORE +
            " WHERE score.fit BETWEEN ? AND ?", (low, high),
        ).fetchall()
        sent = [r for r in rows if r["status"] != "drafting"]
        replied = [r for r in sent if r["status"] in RESPONDED]
        rate = round(100.0 * len(replied) / len(sent)) if sent else None
        out.append({
            "label": label,
            "rate": rate,
            "replied": len(replied),
            "sent": len(sent),
        })
    return out


def next_actions(conn, awaiting):
    actions = []
    if awaiting:
        actions.append({"text": "Rate " + str(awaiting) + " jobs you have not looked at",
                        "state": "do this in chat", "tone": "ok"})
    overdue = conn.execute(
        "SELECT application.id, job.company_name, application.next_action_at"
        " FROM application JOIN job ON job.id = application.job_id"
        " WHERE application.next_action_at IS NOT NULL"
        " AND application.next_action_at < ? LIMIT 5",
        (now().isoformat(timespec="seconds"),),
    ).fetchall()
    for row in overdue:
        actions.append({"text": "Chase up " + (row["company_name"] or "unknown"),
                        "state": "overdue", "tone": "no"})
    if not actions:
        actions.append({"text": "Nothing waiting on you. Press Find jobs to look for more.",
                        "state": "all clear", "tone": "ok"})
    return actions


def sources(conn):
    last = conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 1").fetchone()
    detail = _json(last["detail"]) if last else None
    known = conn.execute("SELECT name, kind FROM source ORDER BY name").fetchall()
    rows = []
    for src in known:
        note = (detail or {}).get(src["name"])
        rows.append({
            "name": src["name"],
            "kind": src["kind"],
            "detail": note,
            "state": "done" if note and "failed" not in str(note) else "idle",
        })
    return {
        "last_run": dict(last) if last else None,
        "sources": rows,
        "dedup": dedup_module.summary(conn),
        "breakdown": breakdown(conn),
    }


def breakdown(conn):
    def group(column, labels=None):
        out = []
        for row in conn.execute(
            "SELECT COALESCE(" + column + ", 'unknown') AS k, COUNT(*) AS n"
            " FROM job GROUP BY k ORDER BY n DESC"
        ):
            key = row["k"]
            out.append({
                "key": (labels or {}).get(key, key),
                "value": key,
                "count": row["n"],
            })
        return out

    passed = conn.execute(
        "SELECT COALESCE(remote, 'unknown') AS k, COUNT(*) AS n FROM job"
        " WHERE gate_status = 'passed' GROUP BY k"
    ).fetchall()
    by_source = conn.execute(
        "SELECT source.name AS name, COUNT(DISTINCT job.id) AS n"
        " FROM job, json_each(job.source_ids) je"
        " JOIN source ON source.id = je.value"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY source.name ORDER BY n DESC"
    ).fetchall()
    return {
        "work_mode": group("remote"),
        "country": group("country"),
        "sponsorship": group("sponsorship_status"),
        "language": group("language_required", {"de": "German", "en": "English"}),
        "work_mode_passed": [{"key": r["k"], "count": r["n"]} for r in passed],
        "by_source": [{"key": r["name"], "count": r["n"]} for r in by_source],
    }


def applications(conn):
    counts = {status: 0 for status in FUNNEL}
    for row in conn.execute(
        "SELECT status, COUNT(*) AS n FROM application GROUP BY status"
    ):
        counts[row["status"]] = row["n"]
    rows = conn.execute(
        "SELECT application.id, application.status, application.applied_at,"
        " application.next_action, application.next_action_at,"
        " job.id AS job_id, job.title, job.company_name, job.url,"
        " job.city, job.country, score.fit, " + EFFECTIVE_REACH + " AS reach"
        " FROM application JOIN job ON job.id = application.job_id" + LATEST_SCORE +
        " ORDER BY application.applied_at DESC, application.id DESC"
    ).fetchall()
    responded = sum(counts[s] for s in RESPONDED if s != "rejected") + counts["rejected"]
    return {
        "funnel": [{"key": s, "value": counts[s]} for s in FUNNEL],
        "rows": [dict(r) for r in rows],
        # A second read on the same numbers: not "what stage", but "have they
        # even heard back" - drafting hasn't been sent, applied is a still-open
        # wait, and screening/interview/offer/rejected all count as a reply.
        "response_mix": [
            {"key": "drafting", "label": "Still drafting", "tone": "slate",
             "value": counts["drafting"]},
            {"key": "awaiting", "label": "Awaiting a reply", "tone": "amber",
             "value": counts["applied"]},
            {"key": "responded", "label": "Heard back", "tone": "pine",
             "value": responded},
        ],
    }


def start_application(conn, job_id):
    exists = conn.execute("SELECT 1 FROM job WHERE id = ?", (job_id,)).fetchone()
    if not exists:
        return None
    return store.start_application(conn, job_id)


def set_application_status(conn, application_id, status, note=None):
    cur = conn.execute(
        "UPDATE application SET status = ? WHERE id = ?", (status, application_id)
    )
    if cur.rowcount == 0:
        conn.commit()
        return None
    stamp = now().isoformat(timespec="seconds")
    if status == "applied":
        conn.execute(
            "UPDATE application SET applied_at = COALESCE(applied_at, ?) WHERE id = ?",
            (stamp, application_id),
        )
    conn.execute(
        "INSERT INTO application_event (application_id, event, note, created_at)"
        " VALUES (?, ?, ?, ?)",
        (application_id, status, note, stamp),
    )
    conn.commit()
    return {"id": application_id, "status": status, "note": note}


def rate_job(conn, job_id, master, user_profile, limits=None, timeout=None):
    brief = job_brief(conn, job_id, master)
    if brief is None:
        return None
    limits = limits or DEFAULT_BANDS
    stored = store.get_reach(conn, job_id)
    reach = stored["reach"] if stored else 0
    provider = get_ai_provider(conn)
    kwargs = {"timeout": timeout} if timeout else {}
    result = rating.score(brief, master, user_profile, reach, limits,
                           provider=provider, **kwargs)
    save_score(
        conn, job_id,
        fit=result["fit"],
        dimensions=result["dimensions"],
        rationale=result["rationale"],
        ats_score=result["ats_score"],
        offer_probability=result["offer_probability"],
        estimate_note=result["estimate_note"],
        model=agent.PROVIDERS[provider]["label"],
    )
    return job_detail(conn, job_id, master)


class NotRatedError(Exception):
    pass


def rate_estimate(conn, job_id, master, user_profile, kind, timeout=None):
    brief = job_brief(conn, job_id, master)
    if brief is None:
        return None
    existing = store.get_score(conn, job_id)
    if existing is None:
        raise NotRatedError("This job has no match score yet.")
    stored = store.get_reach(conn, job_id)
    reach = stored["reach"] if stored else 0
    kwargs = {"timeout": timeout} if timeout else {}
    result = rating.estimate(
        brief, master, user_profile,
        existing["fit"], existing.get("rationale"), reach, kind,
        provider=get_ai_provider(conn), **kwargs
    )
    store.upsert_score(conn, {
        "job_id": job_id,
        "profile_version": existing.get("profile_version", "v1"),
        "rubric_version": existing.get("rubric_version", "v1"),
        "model": existing.get("model"),
        "fit": existing["fit"],
        "reach": existing["reach"],
        "dimensions": _json(existing.get("dimensions")),
        "rationale": existing.get("rationale"),
        "ats_score": result["value"] if kind == "ats" else existing.get("ats_score"),
        "offer_probability": (
            result["value"] if kind == "offer" else existing.get("offer_probability")
        ),
        "estimate_note": result["note"],
    })
    return job_detail(conn, job_id, master)


def job_chat(conn, job_id):
    return store.get_chat(conn, job_id)


def ask_about_job(conn, job_id, master, question, timeout=None):
    brief = job_brief(conn, job_id, master,
                       description_chars=chat_module.MAX_DESCRIPTION_CHARS)
    if brief is None:
        return None
    history = store.get_chat(conn, job_id)
    kwargs = {"timeout": timeout} if timeout else {}
    answer = chat_module.ask(brief, history, question,
                              provider=get_ai_provider(conn), **kwargs)
    history = history + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    store.save_chat(conn, job_id, history)
    return answer


def generate_cv(conn, job_id, master, timeout=None):
    job = job_detail(conn, job_id, master)
    if job is None:
        return None
    kwargs = {"timeout": timeout} if timeout else {}
    result = documents_module.tailor_cv(job, master, provider=get_ai_provider(conn), **kwargs)
    store.save_document(
        conn, job_id, "cv",
        payload=result,
        master_version=(master.get("identity") or {}).get("name"),
    )
    conn.execute("DELETE FROM document WHERE job_id = ? AND kind = 'review'", (job_id,))
    conn.commit()
    # Generating a draft is only a preview - the job is not "applied" until the
    # candidate actually saves it, which accept_document handles.
    result["job"] = {"id": job["id"], "title": job["title"], "company": job["company"]}
    return result


def generate_letter(conn, job_id, master, user_profile, timeout=None):
    job = job_detail(conn, job_id, master)
    if job is None:
        return None
    kwargs = {"timeout": timeout} if timeout else {}
    result = documents_module.cover_letter(
        job, master, user_profile, provider=get_ai_provider(conn), **kwargs
    )
    letter_prefs = (user_profile or {}).get("cover_letter") or {}
    sign_off = (
        letter_prefs.get("sign_off")
        or (user_profile or {}).get("name")
        or (master.get("identity") or {}).get("name")
    )
    result["sign_off"] = sign_off
    store.save_document(
        conn, job_id, "letter",
        body=result["body"],
        payload={"note": result.get("note"), "sign_off": sign_off},
        word_count=result["word_count"],
        master_version=(master.get("identity") or {}).get("name"),
    )
    result["job"] = {"id": job["id"], "title": job["title"], "company": job["company"]}
    return result


def stored_document(conn, job_id, kind):
    row = store.get_document(conn, job_id, kind)
    if not row:
        return None
    row["payload"] = _json(row.get("payload"))
    row["has_file"] = bool(row.get("path")) and Path(row["path"]).exists()
    return row


def accept_document(conn, job_id, kind, master, documents_dir="documents",
                    accent=palette.DEFAULT_ACCENT):
    row = store.get_document(conn, job_id, kind)
    if not row:
        return None
    job = conn.execute(
        "SELECT company_name FROM job WHERE id = ?", (job_id,)
    ).fetchone()
    identity = (master or {}).get("identity") or {}
    company_name = job["company_name"] if job else "job"
    default_dir = render.folder(documents_dir, job_id, company_name)

    name_slug = re.sub(r"[^A-Za-z0-9]+", "_", identity.get("name") or "CV").strip("_")
    company_slug = re.sub(r"[^A-Za-z0-9]+", "_", company_name or "").strip("_")
    suffix = ("_" + company_slug) if company_slug else ""
    default_filename = (
        name_slug + ("_CV" if kind == "cv" else "_Cover_Letter") + suffix + ".docx"
    )

    chosen = render.ask_save_path(default_dir, default_filename)
    if chosen is None:
        return {"job_id": job_id, "kind": kind, "cancelled": True}

    if kind == "cv":
        payload = _json(row.get("payload")) or {}
        content = payload.get("structured")
        if not content:
            return {"error": "This draft was made before previews were added. "
                             "Write it again, then save."}
        path = render.cv_docx(content, chosen, accent=accent)
    else:
        path = render.letter_docx(row.get("body") or "", identity, chosen)
    conn.execute(
        "UPDATE document SET accepted = 1, path = ? WHERE id = ?",
        (str(path), row["id"]),
    )
    conn.commit()
    application = store.start_application(conn, job_id)
    return {
        "job_id": job_id, "kind": kind, "accepted": True, "path": str(path),
        "application_status": application["status"] if application else None,
    }


class ExportUnavailable(Exception):
    pass


def export_cv(conn, job_id, fmt, accent=palette.DEFAULT_ACCENT):
    row = store.get_document(conn, job_id, "cv")
    if not row:
        return None
    payload = _json(row.get("payload")) or {}
    content = payload.get("structured")
    if not content:
        raise ExportUnavailable(
            "This draft was made before downloads were added. Write it again."
        )
    buf = io.BytesIO()
    (render.cv_docx if fmt == "docx" else pdf.cv_pdf)(content, buf, accent=accent)
    buf.seek(0)
    identity = content.get("identity") or {}
    name_slug = re.sub(r"[^A-Za-z0-9]+", "_", identity.get("name") or "CV").strip("_")
    return {"data": buf, "filename": name_slug + "_CV." + fmt}


class NoTailoredCvError(Exception):
    pass


def review_cv(conn, job_id, master, timeout=None):
    job = job_detail(conn, job_id, master)
    if job is None:
        return None
    cv_row = store.get_document(conn, job_id, "cv")
    payload = _json(cv_row.get("payload")) if cv_row else None
    cv_text = (payload or {}).get("rendered")
    if not cv_text:
        raise NoTailoredCvError("Write a CV for this job first, then review it.")
    kwargs = {"timeout": timeout} if timeout else {}
    result = documents_module.review_cv(job, cv_text, provider=get_ai_provider(conn), **kwargs)
    store.save_document(conn, job_id, "review", payload=result)
    return result


def stored_review(conn, job_id):
    row = store.get_document(conn, job_id, "review")
    if not row:
        return None
    return _json(row.get("payload"))


def add_cv_highlight(conn, job_id, master, text, topic=None):
    text = (text or "").strip()
    topic = (topic or "").strip()
    if not text:
        raise ValueError("Nothing to add.")
    job = job_detail(conn, job_id, master)
    if job is None:
        return None
    cv_row = store.get_document(conn, job_id, "cv")
    payload = _json(cv_row.get("payload")) if cv_row else None
    content = (payload or {}).get("structured")
    if not content:
        raise ExportUnavailable(
            "This draft was made before highlights were added. Write it again, then try again."
        )
    sections = content.get("sections") or []
    highlights = next((s for s in sections if s["kind"] == "highlights"), None)
    if highlights is None:
        highlights = {"kind": "highlights", "heading": "ADDITIONAL HIGHLIGHTS", "items": []}
        exp_index = next(
            (i for i, s in enumerate(sections) if s["kind"] == "experience"),
            len(sections) - 1,
        )
        sections.insert(exp_index + 1, highlights)
    # Stored as a dict once a topic is known; plain strings stay readable
    # so drafts saved before topics existed still render.
    entry = tailor.ascii_safe(text)
    if topic:
        entry = {"topic": tailor.ascii_safe(topic), "text": entry}
    highlights["items"].append(entry)
    content["sections"] = sections
    result = tailor.derive_cv_result(
        content, payload.get("changes") or [], payload.get("note"), job, master
    )
    store.save_document(
        conn, job_id, "cv",
        payload=result,
        master_version=((master or {}).get("identity") or {}).get("name"),
    )
    return result


def discard_document(conn, job_id, kind):
    row = store.get_document(conn, job_id, kind)
    if not row:
        return None
    if row.get("path"):
        target = Path(row["path"])
        if target.exists():
            target.unlink()
    conn.execute("DELETE FROM document WHERE id = ?", (row["id"],))
    conn.commit()
    return {"job_id": job_id, "kind": kind, "discarded": True}


def documents(conn, job_id):
    rows = conn.execute(
        "SELECT id, kind, path, master_version, created_at FROM document"
        " WHERE job_id = ? ORDER BY created_at DESC", (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def all_documents(conn):
    rows = conn.execute(
        "SELECT document.id, document.job_id, document.kind, document.path,"
        " document.created_at, job.title, job.company_name"
        " FROM document JOIN job ON job.id = document.job_id"
        " WHERE document.accepted = 1 ORDER BY document.created_at DESC"
    ).fetchall()
    return [
        {
            "id": r["id"], "job_id": r["job_id"], "kind": r["kind"],
            "has_file": bool(r["path"]) and Path(r["path"]).exists(),
            "created_at": r["created_at"], "title": r["title"],
            "company": r["company_name"],
        }
        for r in rows
    ]


def master_cv(master=None):
    if not master:
        return {
            "available": False,
            "tiers": {tier: [] for tier in profile.TIERS},
            "pending": [],
            "hint": "master.yaml not found. Copy master.example.yaml to"
                    " master.yaml and fill it in to enable CV tailoring.",
        }
    return {
        "available": True,
        "tiers": profile.skill_tiers(master),
        "pending": master.get("pending_keywords") or [],
        "hint": None,
    }


MASTER_UPLOAD_KINDS = ("cv",)
MASTER_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt", ".md", ".rtf")


def _master_upload_dir(documents_dir):
    path = Path(documents_dir) / "master"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_text(path):
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs).strip() or None
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text.strip() or None
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except Exception:
        return None
    return None


def save_master_upload(documents_dir, kind, filename, content):
    if kind not in MASTER_UPLOAD_KINDS:
        raise ValueError("kind must be cv or letter")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in MASTER_UPLOAD_EXTENSIONS:
        raise ValueError(
            "unsupported file type " + suffix + ", use one of " +
            ", ".join(MASTER_UPLOAD_EXTENSIONS)
        )
    folder = _master_upload_dir(documents_dir)
    target = folder / (kind + suffix)
    for existing in folder.glob(kind + ".*"):
        existing.unlink()
    target.write_bytes(content)
    text = _extract_text(target)
    if text:
        (folder / (kind + ".txt")).write_text(text, encoding="utf-8")
    meta = {
        "filename": Path(filename).name,
        "uploaded_at": now().isoformat(timespec="seconds"),
        "has_text": bool(text),
    }
    (folder / (kind + ".meta.json")).write_text(json.dumps(meta), encoding="utf-8")
    meta["kind"] = kind
    meta["has_file"] = True
    return meta


def master_upload_info(documents_dir, kind):
    folder = _master_upload_dir(documents_dir)
    meta_path = folder / (kind + ".meta.json")
    if not meta_path.exists():
        return None
    meta = _json(meta_path.read_text(encoding="utf-8")) or {}
    stored = next(
        (p for p in folder.glob(kind + ".*") if p.suffix not in (".json", ".txt")),
        None,
    )
    meta["kind"] = kind
    meta["has_file"] = bool(stored and stored.exists())
    text_path = folder / (kind + ".txt")
    if text_path.exists():
        meta["preview"] = text_path.read_text(encoding="utf-8")
        meta["preview_truncated"] = False
    else:
        meta["preview"] = None
        meta["preview_truncated"] = False
    return meta


def master_upload_path(documents_dir, kind):
    folder = _master_upload_dir(documents_dir)
    return next(
        (p for p in folder.glob(kind + ".*") if p.suffix not in (".json", ".txt")),
        None,
    )


def discard_master_upload(documents_dir, kind):
    folder = _master_upload_dir(documents_dir)
    matches = list(folder.glob(kind + ".*"))
    for p in matches:
        p.unlink()
    return bool(matches)


def extract_skills(conn, master, text, timeout=None):
    kwargs = {"timeout": timeout} if timeout else {}
    existing = profile.existing_names(master)
    return skills_module.extract(text, existing, provider=get_ai_provider(conn), **kwargs)


def save_skills(master, master_path, entries):
    additions, added, skipped = skills_module.merge(master, entries)
    if added:
        profile.append_skills(master_path, additions)
    updated = profile.load_master(master_path) or master
    return {
        "tiers": profile.skill_tiers(updated),
        "added": added,
        "skipped": skipped,
    }


SKILL_GAP_KEY = "skill_gap_cache"


def _recent_posting_text(conn, limit=20):
    rows = conn.execute(
        "SELECT title, company_name, description FROM job"
        " WHERE gate_status = 'passed' AND description IS NOT NULL"
        " ORDER BY posted_at DESC LIMIT ?", (limit,)
    ).fetchall()
    parts = []
    for row in rows:
        parts.append(
            "### " + (row["title"] or "") + " at " + (row["company_name"] or "") + "\n"
            + (row["description"] or "")[:1200]
        )
    return "\n\n".join(parts)


def skill_gaps(conn, master):
    cached = store.get_setting(conn, SKILL_GAP_KEY)
    if not cached:
        return {"computed_at": None, "gaps": []}
    return json.loads(cached)


def refresh_skill_gaps(conn, master, timeout=None):
    postings = _recent_posting_text(conn)
    existing = profile.existing_names(master)
    kwargs = {"timeout": timeout} if timeout else {}
    gaps = skills_module.find_gaps(postings, existing, provider=get_ai_provider(conn), **kwargs)
    result = {"computed_at": now().isoformat(timespec="seconds"), "gaps": gaps}
    store.set_setting(conn, SKILL_GAP_KEY, json.dumps(result))
    return result


def skill_demand(conn, master, sample=500, top=12):
    tiers = profile.skill_tiers(master)
    entries = [
        {"name": item["name"], "tier": tier}
        for tier, items in tiers.items() for item in items
    ]
    if not entries:
        return []
    rows = conn.execute(
        "SELECT description FROM job WHERE description IS NOT NULL"
        " ORDER BY posted_at DESC LIMIT ?", (sample,)
    ).fetchall()
    counts = {e["name"]: 0 for e in entries}
    for row in rows:
        matched = profile.match_skills(master, row["description"])
        for tier_matches in matched.values():
            for m in tier_matches:
                if m["name"] in counts:
                    counts[m["name"]] += 1
    tone = {"core": "pine", "working": "mint", "familiar": "slate"}
    ranked = sorted(entries, key=lambda e: counts[e["name"]], reverse=True)
    return [
        {"key": e["name"], "label": e["name"], "tone": tone[e["tier"]], "value": counts[e["name"]]}
        for e in ranked[:top]
    ]


def profile_freshness(conn, master_path):
    path = Path(master_path)
    if not path.exists():
        return {"available": False}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    since_iso = mtime.isoformat(timespec="seconds")
    jobs_rated_since = conn.execute(
        "SELECT COUNT(*) AS n FROM score WHERE scored_at >= ?", (since_iso,)
    ).fetchone()["n"]
    return {
        "available": True,
        "updated_at": since_iso,
        "days_since": (now() - mtime).days,
        "jobs_rated_since": jobs_rated_since,
    }


def bullet_usage(conn, master):
    known = known_bullets(master)
    rows = conn.execute(
        "SELECT payload FROM document WHERE kind = 'cv' AND payload IS NOT NULL"
    ).fetchall()
    tally = {}
    considered = 0
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except ValueError:
            continue
        changes = payload.get("changes") or []
        if not changes:
            continue
        considered += 1
        for change in changes:
            bullet_id = change.get("id")
            action = change.get("action")
            if not bullet_id or bullet_id not in known:
                continue
            entry = tally.setdefault(bullet_id, {"kept": 0, "dropped": 0, "total": 0})
            entry["total"] += 1
            if action == "dropped":
                entry["dropped"] += 1
            else:
                entry["kept"] += 1
    bullets = []
    for bullet_id, counts in tally.items():
        if counts["total"] < 2:
            continue
        info = known[bullet_id]
        bullets.append({
            "id": bullet_id,
            "text": info["text"],
            "company": info["company"],
            "kept": counts["kept"],
            "dropped": counts["dropped"],
            "total": counts["total"],
            "drop_rate": round(counts["dropped"] / counts["total"] * 100),
        })
    bullets.sort(key=lambda b: b["drop_rate"], reverse=True)
    return {"documents_considered": considered, "bullets": bullets[:8]}


def gmail_status(conn, cfg):
    gcfg = cfg.get("gmail") or {}
    token = gmail_auth.load_token(conn)
    last = store.latest_gmail_sync(conn)
    pending = len(store.pending_email_suggestions(conn))
    secret_path = gcfg.get("client_secret_path", "gmail_client_secret.json")
    # Either a pasted Client ID/Secret or a downloaded JSON file counts -
    # resolve_client() prefers the pasted one but accepts either.
    credentials_present = bool(gmail_auth.load_saved_client(conn)) or Path(secret_path).exists()
    return {
        "connected": bool(token and token.get("refresh_token")),
        "account_email": (token or {}).get("account_email"),
        "credentials_present": credentials_present,
        "last_sync": last,
        "pending_suggestions": pending,
    }


def gmail_save_credentials(conn, client_id, client_secret):
    return gmail_auth.save_client(conn, client_id, client_secret)


def gmail_connect(conn, cfg):
    gcfg = cfg.get("gmail") or {}
    return gmail_auth.connect(conn, gcfg.get("client_secret_path", "gmail_client_secret.json"))


def gmail_sync_and_match(conn, cfg):
    result = gmail_sync.run(conn, cfg)
    result.update(gmail_match.run(conn))
    return result


def gmail_suggestions(conn):
    return [
        {
            "email_id": r["id"],
            "application_id": r["application_id"],
            "job_id": r["job_id"],
            "title": r["title"],
            "company": r["company_name"],
            "current_status": r["current_status"],
            "suggested_status": r["suggested_status"],
            "subject": r["subject"],
            "sender": r["sender"],
            "snippet": r["snippet"],
            "received_at": r["received_at"],
        }
        for r in store.pending_email_suggestions(conn)
    ]


def apply_gmail_suggestion(conn, email_id):
    email = store.get_application_email(conn, email_id)
    if not email or not email.get("application_id") or not email.get("suggested_status"):
        return None
    set_application_status(
        conn, email["application_id"], email["suggested_status"],
        note="from a Gmail reply",
    )
    store.mark_application_email_reviewed(conn, email_id)
    return {"email_id": email_id, "status": email["suggested_status"]}


def dismiss_gmail_suggestion(conn, email_id):
    email = store.get_application_email(conn, email_id)
    if not email:
        return None
    store.mark_application_email_reviewed(conn, email_id)
    return {"email_id": email_id, "dismissed": True}


def sponsorship_mix(conn):
    rows = conn.execute(
        "SELECT job.sponsorship_status AS status, COUNT(*) AS n FROM job"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed' AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY job.sponsorship_status"
    ).fetchall()
    counts = {"confirmed": 0, "unknown": 0, "denied": 0}
    for row in rows:
        key = row["status"] if row["status"] in counts else "unknown"
        counts[key] += row["n"]
    tone = {"confirmed": "pine", "unknown": "amber", "denied": "rust"}
    label = {"confirmed": "Confirmed", "unknown": "Unknown", "denied": "Denied"}
    return [
        {"key": key, "label": label[key], "tone": tone[key], "value": counts[key]}
        for key in ("confirmed", "unknown", "denied")
    ]


def language_mix(conn):
    """English-only vs German-required, among the same jobs sponsorship_mix
    counts - the two other factors (language, agency) get the same treatment
    so all three sit on the Profile page together."""
    rows = conn.execute(
        "SELECT job.language_required AS lang, COUNT(*) AS n FROM job"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed' AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY job.language_required"
    ).fetchall()
    counts = {"english": 0, "german": 0}
    for row in rows:
        counts["german" if row["lang"] == "de" else "english"] += row["n"]
    return [
        {"key": "english", "label": "English is enough", "tone": "pine",
         "value": counts["english"]},
        {"key": "german", "label": "German needed", "tone": "amber",
         "value": counts["german"]},
    ]


def agency_mix(conn):
    """Posted directly by the employer vs through a staffing agency."""
    rows = conn.execute(
        "SELECT job.via_agency AS agency, COUNT(*) AS n FROM job"
        " LEFT JOIN application ON application.job_id = job.id"
        " WHERE job.gate_status = 'passed' AND job.status NOT IN ('hidden', 'rejected')"
        " AND application.applied_at IS NULL"
        " GROUP BY job.via_agency"
    ).fetchall()
    counts = {"direct": 0, "agency": 0}
    for row in rows:
        counts["agency" if row["agency"] else "direct"] += row["n"]
    return [
        {"key": "direct", "label": "Posted by the company", "tone": "pine",
         "value": counts["direct"]},
        {"key": "agency", "label": "Posted by an agency", "tone": "amber",
         "value": counts["agency"]},
    ]


def keyword_coverage(conn, sample=10):
    rows = conn.execute(
        "SELECT document.job_id, document.payload, document.created_at,"
        " job.title, job.company_name FROM document"
        " JOIN job ON job.id = document.job_id"
        " WHERE document.kind = 'cv' AND document.payload IS NOT NULL"
        " ORDER BY document.created_at DESC LIMIT ?", (sample,)
    ).fetchall()
    jobs = []
    percentages = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except ValueError:
            continue
        counts = (payload.get("keywords") or {}).get("counts") or {}
        total = counts.get("covered", 0) + counts.get("fixable", 0) + counts.get("real_gap", 0)
        if not total:
            continue
        pct = round(counts.get("covered", 0) / total * 100)
        percentages.append(pct)
        jobs.append({
            "key": str(row["job_id"]),
            "label": (row["title"] or "") + " @ " + (row["company_name"] or ""),
            "tone": "pine" if pct >= 66 else ("amber" if pct >= 40 else "rust"),
            "value": pct,
        })
    average = round(sum(percentages) / len(percentages)) if percentages else None
    return {"average": average, "jobs": jobs}
