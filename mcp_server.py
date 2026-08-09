import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:
    from mcp.server.fastmcp import FastMCP as Server

from jobagent import config, profile, pull, service, store

ROOT = Path(__file__).resolve().parent
if os.environ.get("JOBAGENT_HOME"):
    ROOT = Path(os.environ["JOBAGENT_HOME"])

mcp = Server("jobagent")


def cfg():
    return config.load(str(ROOT / "config.yaml"))


def db(settings=None):
    settings = settings or cfg()
    path = settings["db_path"]
    if not Path(path).is_absolute():
        path = str(ROOT / path)
    conn = store.connect(path)
    store.migrate(conn)
    return conn


def master(settings=None):
    settings = settings or cfg()
    path = settings.get("master_path", "master.yaml")
    if not Path(path).is_absolute():
        path = str(ROOT / path)
    return profile.load_master(path)


def line(job):
    scores = job["scores"]
    parts = [
        "id " + str(job["id"]),
        job["title"] or "untitled",
        "at " + (job["company"] or "unknown"),
    ]
    if job.get("band") and job["band"] != "unrated":
        parts.append("band " + job["band"])
    where = ", ".join(x for x in [job.get("city"), job.get("country")] if x)
    if where:
        parts.append("in " + where)
    if job.get("posted_age"):
        parts.append("posted " + job["posted_age"])
    if scores.get("fit") is not None:
        parts.append("fit " + str(scores["fit"]) + ", reach " + str(scores["reach"]))
    parts.append(job.get("sponsorship") or "sponsorship unknown")
    return " | ".join(parts)


@mcp.tool()
def pull_jobs(countries: list[str] | None = None, since_days: int | None = None) -> str:
    """Fetch new job postings from the enabled sources into the local database."""
    settings = cfg()
    conn = db(settings)
    try:
        result = pull.run(conn, settings, countries, since_days)
        detail = "; ".join(k + ": " + str(v) for k, v in result["detail"].items())
        return (
            "Checked " + str(result["raw"]) + " listings and added "
            + str(result["new"]) + " new jobs. " + detail
        )
    finally:
        conn.close()


@mcp.tool()
def get_pending(limit: int = 50) -> str:
    """List jobs that passed the rules gate but have no fit score yet.

    The reply says how many are still waiting after this batch. If that number is
    above zero, call this again and keep going until it reaches zero.
    """
    conn = db()
    try:
        jobs = service.pending_jobs(conn, limit)
        remaining = service.pending_count(conn)
        if not jobs:
            return "Nothing is waiting to be scored."
        head = (
            "Showing " + str(len(jobs)) + " of " + str(remaining)
            + " job(s) that still need scoring. Call get_job_brief for detail."
        )
        left = remaining - len(jobs)
        tail = (
            "\n\n" + str(left) + " more still need scoring after these. Call "
            "get_pending again when you have saved this batch."
        ) if left > 0 else "\n\nThis is all of them."
        return head + "\n" + "\n".join(line(j) for j in jobs) + tail
    finally:
        conn.close()


@mcp.tool()
def get_job_brief(job_id: int) -> dict:
    """Get the full posting text and stored facts for one job, ready to score."""
    settings = cfg()
    conn = db(settings)
    try:
        brief = service.job_brief(conn, job_id, master(settings))
        if brief is None:
            return {"error": "no job with id " + str(job_id)}
        brief.pop("documents", None)
        brief.pop("neighbours", None)
        return brief
    finally:
        conn.close()


SAVE_SCORES_DOC = """Store the fit score for one or more jobs.

Each item needs job_id and fit as an integer from 0 to 100. Optional:
dimensions (a dict of rubric part to points), rationale, ats_score,
offer_probability, estimate_note.

Do NOT send reach. reach is computed in Python from facts in the advert -
sponsorship, language, direct employer or agency, how old the advert is, and
whether the salary clears the Blue Card threshold. Anything you send in a reach
field is ignored in favour of the computed number.

fit is merit. reach is whether the job is realistically landable. Never average
them, and never return a single combined number.

Fill ats_score and offer_probability ONLY when the job you are scoring reaches
fit {strong_match} or more AND reach {strong_chance} or more. Those jobs are the
ones the user will actually pursue, so the extra estimates are worth having. For
anything below that bar leave both fields out rather than guessing, because they
cost effort and nobody acts on them.

When you do supply them, set estimate_note to a short sentence saying they are
your estimate rather than a measurement. No applicant tracking system publishes
a score, and nothing in a job advert predicts an offer.
"""


@mcp.tool(description=SAVE_SCORES_DOC.format(**service.band_limits(config.load())))
def save_scores(scores: list[dict]) -> str:
    conn = db()
    incoming = [{k: v for k, v in item.items() if k != "reach"} for item in scores]
    try:
        result = service.save_scores(conn, incoming, model="claude")
    except ValueError as exc:
        return "Nothing saved. " + str(exc)
    finally:
        conn.close()
    saved = result["saved"]
    text = "Saved scores for " + str(len(saved)) + " job(s)."
    if saved:
        text += " " + ", ".join(
            "id " + str(s["job_id"]) + " fit " + str(s["fit"]) + " reach " + str(s["reach"])
            for s in saved
        )
    if result["unknown_job_ids"]:
        text += " No job found for id " + ", ".join(str(i) for i in result["unknown_job_ids"]) + "."
    return text


@mcp.tool()
def mark(marks: list[dict]) -> str:
    """Shortlist, hide or reject jobs in one call.

    Each item needs job_id and action, where action is shortlist, hide, reject
    or reset. Optional reason. Batch them so triaging many jobs is one approval.
    """
    conn = db()
    try:
        result = service.mark_many(conn, marks)
    except ValueError as exc:
        return "Nothing changed. " + str(exc)
    finally:
        conn.close()
    text = "Updated " + str(len(result["marked"])) + " job(s)."
    for item in result["marked"]:
        text += " id " + str(item["id"]) + " is now " + item["status"] + "."
    if result["unknown_job_ids"]:
        text += " No job found for id " + ", ".join(str(i) for i in result["unknown_job_ids"]) + "."
    return text


@mcp.tool()
def top_jobs(limit: int = 10, min_fit: int | None = None) -> str:
    """List the best scored jobs, highest fit first."""
    conn = db()
    try:
        jobs = service.top_jobs(conn, limit, min_fit)
        if not jobs:
            return "No scored jobs yet. Run get_pending, then save_scores."
        return "\n".join(line(j) for j in jobs)
    finally:
        conn.close()


@mcp.tool()
def render_dashboard() -> str:
    """Summarise the current state of the job search in plain language."""
    conn = db()
    try:
        data = service.dashboard(conn)
    finally:
        conn.close()
    lines = [c["key"] + ": " + str(c["value"]) + " (" + c["sub"] + ")" for c in data["cards"]]
    lines.append("Next: " + "; ".join(a["text"] for a in data["next_actions"]))
    return "\n".join(lines)


@mcp.tool()
def get_master_cv() -> dict:
    """Read the tiered skills from master.yaml, or report that it is missing."""
    return service.master_cv(master())


if __name__ == "__main__":
    mcp.run()
