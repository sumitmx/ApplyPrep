import concurrent.futures
import json
from datetime import datetime, timedelta, timezone

from . import normalize as norm
from . import profile as profile_module
from . import reach as reach_module
from . import store, watchlist
from .adapters.aggregator.adzuna import Adzuna
from .adapters.aggregator.arbeitnow import Arbeitnow
from .adapters.aggregator.remoteok import RemoteOK
from .adapters.aggregator.remotive import Remotive
from .adapters.aggregator.wwr import WeWorkRemotely
from .adapters.ats.ashby import Ashby
from .adapters.ats.greenhouse import Greenhouse
from .adapters.ats.lever import Lever
from .adapters.ats.workable import Workable
from .gate import evaluate

REGISTRY = {
    "arbeitnow": Arbeitnow,
    "remotive": Remotive,
    "remoteok": RemoteOK,
    "wwr": WeWorkRemotely,
    "adzuna": Adzuna,
}

ATS_REGISTRY = {
    "greenhouse": Greenhouse,
    "lever": Lever,
    "ashby": Ashby,
    "workable": Workable,
}


def load_profile(cfg):
    return profile_module.load_profile(cfg.get("profile_path", "profile.yaml")) or {}


def sync_watchlist(conn, cfg):
    companies = watchlist.load(cfg.get("watchlist_path", "watchlist.yaml"))
    for company in companies:
        store.upsert_company(
            conn, company["name"], company["slug"], company["ats"], company["token"]
        )
    return companies


def adapters_for(cfg, companies, only=None):
    grouped = watchlist.by_kind(companies)
    sources = cfg.get("sources") or {}
    out = []
    for name, cls in REGISTRY.items():
        settings = sources.get(name) or {}
        if settings.get("enabled") and (not only or name in only):
            out.append((name, cls(), settings))
    for name, cls in ATS_REGISTRY.items():
        settings = sources.get(name) or {}
        members = grouped.get(name) or []
        if settings.get("enabled") and members and (not only or name in only):
            out.append((name, cls(members), settings))
    return out


# Sources have nothing to do with each other, so a run should cost as long as
# its slowest source rather than the sum of all of them. Only the fetching is
# shared out: every database write stays on the caller's thread, because the
# whole app runs on a single sqlite connection.
FETCH_WORKERS = 6


def fetch_all(adapters, countries, since_days, workers=FETCH_WORKERS):
    """Ask every source at once. Network only - nothing here touches the database.

    Hands back {name: (postings, error)} so one source failing costs only that
    source. A source that raises reports its reason and the rest still land.
    """
    results = {}
    if not adapters:
        return results
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(workers, len(adapters)))
    )
    try:
        pending = {
            pool.submit(adapter.fetch, settings, countries, since_days): name
            for name, adapter, settings in adapters
        }
        for future in concurrent.futures.as_completed(pending):
            name = pending[future]
            try:
                results[name] = (future.result(), None)
            except Exception as exc:
                results[name] = ([], str(exc))
    finally:
        pool.shutdown(wait=False)
    return results


def ingest(conn, cfg, prof, name, src_id, postings, slugs, master=None):
    added = 0
    failed = 0
    first_error = None
    reaches = []

    for raw in postings:
        try:
            job = norm.normalize(name, raw, src_id)
            job_id, is_new = store.upsert_job(conn, job)
        except Exception as exc:
            failed += 1
            if first_error is None:
                first_error = str(exc)
            continue
        if not is_new:
            continue
        added += 1
        status, reason = evaluate(job, cfg["gate"], master)
        store.set_gate(conn, job_id, status, reason)
        reaches.append((job_id, reach_module.compute(job, cfg, prof)))
        slug = norm.slugify(job.get("company_name"))
        if slug in slugs:
            store.set_job_company(conn, job_id, slugs[slug])

    if reaches:
        store.save_reach_many(conn, reaches)
    return added, failed, first_error


def run(conn, cfg, countries=None, since_days=None, only=None):
    countries = countries or cfg["countries"]
    since_days = since_days if since_days is not None else cfg["since_days"]
    prof = load_profile(cfg)
    master = profile_module.load_master(cfg.get("master_path", "master.yaml"))
    companies = sync_watchlist(conn, cfg)
    slugs = store.company_ids(conn)
    run_id = store.start_run(conn, countries, since_days)

    raw_total = 0
    new_total = 0
    detail = {}

    adapters = adapters_for(cfg, companies, only)
    fetched = fetch_all(adapters, countries, since_days)

    for name, adapter, settings in adapters:
        postings, error = fetched.get(name, ([], "was not fetched"))
        if error is not None:
            detail[name] = "failed: " + error
            continue

        src_id = store.source_id(conn, name, adapter.kind)
        stored = store.save_raw(conn, run_id, src_id, postings)
        raw_total += stored
        added, failed, first_error = ingest(
            conn, cfg, prof, name, src_id, postings, slugs, master
        )
        new_total += added

        summary = (
            str(len(postings)) + " fetched, " + str(stored) + " stored, "
            + str(added) + " new"
        )
        if failed:
            summary += ", " + str(failed) + " skipped"
        detail[name] = summary
        if first_error:
            detail[name + "_error"] = first_error
        errors = getattr(adapter, "errors", None)
        if errors:
            detail[name + "_unreachable"] = errors

    store.finish_run(conn, run_id, raw_total, new_total, detail)
    result = {"run_id": run_id, "raw": raw_total, "new": new_total, "detail": detail}

    # Sweep out postings that have aged past the gate's freshness window, so the
    # database and every list stay inside it without a manual prune. The window
    # follows gate.max_age_days on purpose: those are exactly the jobs the gate
    # would now reject as stale. prune() still protects shortlisted, applied and
    # hand-pasted jobs. A null max_age_days means "no age limit", so nothing is
    # swept; a non-positive one is ignored rather than emptying the database.
    max_age = (cfg.get("gate") or {}).get("max_age_days")
    if max_age is not None and max_age > 0:
        result["pruned"] = prune(conn, days=max_age, apply=True)

    return result


def recompute_reach(conn, cfg):
    prof = load_profile(cfg)
    pairs = []
    buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-100": 0}
    for job in store.all_jobs(conn):
        data = reach_module.compute(job, cfg, prof)
        pairs.append((job["id"], data))
        value = data["reach"]
        if value < 25:
            buckets["0-24"] += 1
        elif value < 50:
            buckets["25-49"] += 1
        elif value < 75:
            buckets["50-74"] += 1
        else:
            buckets["75-100"] += 1
    if pairs:
        store.save_reach_many(conn, pairs)
    average = round(sum(d["reach"] for _, d in pairs) / len(pairs), 1) if pairs else 0
    return {"jobs": len(pairs), "average": average, "distribution": buckets}


def rebuild(conn, cfg):
    rows = conn.execute(
        "SELECT raw_posting.source_id, raw_posting.external_id, raw_posting.url,"
        " raw_posting.payload, source.name AS source_name"
        " FROM raw_posting JOIN source ON source.id = raw_posting.source_id"
        " ORDER BY raw_posting.id"
    ).fetchall()

    rebuilt = {}
    skipped = 0
    for row in rows:
        raw = {
            "external_id": row["external_id"],
            "url": row["url"],
            "payload": json.loads(row["payload"]),
        }
        try:
            job = norm.normalize(row["source_name"], raw, row["source_id"])
        except Exception:
            skipped += 1
            continue
        rebuilt[job["dedup_key"]] = job

    keep = {}
    drop = []
    for existing in conn.execute("SELECT id, url, status FROM job ORDER BY id"):
        key = norm.canonical_url(existing["url"])
        if key and key in keep:
            drop.append(existing["id"])
        elif key:
            keep[key] = dict(existing)
        else:
            drop.append(existing["id"])

    referenced = set()
    for table in ("score", "application", "document"):
        for row in conn.execute("SELECT DISTINCT job_id FROM " + table):
            referenced.add(row["job_id"])

    blocked = [i for i in drop if i in referenced]
    drop = [i for i in drop if i not in referenced]
    if drop:
        conn.executemany("DELETE FROM job_reach WHERE job_id = ?", [(i,) for i in drop])
        conn.executemany("DELETE FROM job WHERE id = ?", [(i,) for i in drop])

    updated = 0
    inserted = 0
    for job in rebuilt.values():
        match = keep.get(norm.canonical_url(job.get("url")))
        if match:
            conn.execute(
                "UPDATE job SET dedup_key = ?, title = ?, company_name = ?,"
                " country = ?, city = ?, remote = ?, employment_type = ?,"
                " posted_at = ?, url = ?, description = ?, salary_min = ?,"
                " salary_max = ?, salary_currency = ?, sponsorship_status = ?,"
                " language_required = ?, via_agency = ? WHERE id = ?",
                (
                    job["dedup_key"], job["title"], job["company_name"],
                    job.get("country"), job.get("city"), job.get("remote"),
                    job.get("employment_type"), job.get("posted_at"), job["url"],
                    job.get("description"), job.get("salary_min"),
                    job.get("salary_max"), job.get("salary_currency"),
                    job.get("sponsorship_status", "unknown"),
                    job.get("language_required"), 1 if job.get("via_agency") else 0,
                    match["id"],
                ),
            )
            updated += 1
        else:
            store.upsert_job(conn, job)
            inserted += 1
    conn.commit()

    result = {
        "raw_postings": len(rows),
        "unique_jobs": len(rebuilt),
        "updated": updated,
        "inserted": inserted,
        "removed": len(drop),
        "skipped": skipped,
    }
    if blocked:
        result["kept_because_referenced"] = blocked
    result["gate"] = regate(conn, cfg)
    result["reach"] = recompute_reach(conn, cfg)
    return result


def regate(conn, cfg):
    master = profile_module.load_master(cfg.get("master_path", "master.yaml"))
    counts = {}
    updates = []
    for job in store.all_jobs(conn):
        status, reason = evaluate(job, cfg["gate"], master)
        if status != job.get("gate_status") or reason != job.get("gate_reason"):
            updates.append((status, reason, job["id"]))
        counts[status] = counts.get(status, 0) + 1
    store.set_gate_many(conn, updates)
    return {"total": sum(counts.values()), "changed": len(updates), "counts": counts}


def prune(conn, days=7, apply=False):
    """Remove job postings older than `days` (by posted_at) that were never
    engaged with - not shortlisted, no application, no saved document. Jobs
    with no posted_at are left alone since their age can't be determined.
    Dry run by default; pass apply=True to actually delete."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")

    referenced = set()
    for table in ("application", "document"):
        for row in conn.execute("SELECT DISTINCT job_id FROM " + table):
            referenced.add(row["job_id"])

    candidates = conn.execute(
        "SELECT id, source_ids FROM job WHERE posted_at IS NOT NULL"
        " AND posted_at < ? AND status != 'shortlisted'",
        (cutoff,),
    ).fetchall()

    # Hand-pasted jobs are never swept up. They took deliberate effort to enter
    # and cannot be re-pulled from anywhere, so ageing out would lose them.
    row = conn.execute(
        "SELECT id FROM source WHERE name = ?", (PASTED_SOURCE,)
    ).fetchone()
    pasted_id = row["id"] if row else None

    def _pasted(candidate):
        if pasted_id is None:
            return False
        try:
            return pasted_id in json.loads(candidate["source_ids"] or "[]")
        except (TypeError, ValueError):
            return False

    protected = [r for r in candidates if _pasted(r)]
    ageing = [r for r in candidates if not _pasted(r)]

    drop = [r["id"] for r in ageing if r["id"] not in referenced]
    kept = [r["id"] for r in ageing if r["id"] in referenced]

    result = {
        "cutoff": cutoff,
        "eligible": len(drop),
        "kept_because_referenced": len(kept),
        "kept_because_pasted": len(protected),
        "applied": False,
    }
    if apply and drop:
        for table in ("job_reach", "score", "job_chat"):
            conn.executemany("DELETE FROM " + table + " WHERE job_id = ?", [(i,) for i in drop])
        conn.executemany("DELETE FROM job WHERE id = ?", [(i,) for i in drop])
        conn.commit()
        result["applied"] = True
        result["removed"] = len(drop)
    return result


PASTED_SOURCE = "pasted"


def pasted_source_id(conn):
    """The synthetic source every hand-entered job is filed under."""
    return store.source_id(conn, PASTED_SOURCE, "manual")


def paste_job(conn, cfg, fields, master=None, prof=None):
    """Create a job from a description pasted in by hand.

    LinkedIn, Upwork and remote.com cannot be scraped, so this is how a posting
    from one of them enters the pipeline. It runs the same normalisation as a
    pulled job - location, sponsorship, language and agency are all detected
    from the text - so the detail page, rating, CV tailoring and cover letter
    behave identically from here on.

    The gate is the one deliberate difference. Pulled jobs are filtered on
    title and keyword rules because nobody chose them; this one was pasted on
    purpose, so it always passes and is never silently hidden.
    """
    title = (fields.get("title") or "").strip()
    company = (fields.get("company") or "").strip()
    body = (fields.get("description") or "").strip()
    missing = [
        name for name, value in
        (("title", title), ("company", company), ("description", body))
        if not value
    ]
    if missing:
        raise ValueError("these are required: " + ", ".join(missing))

    src_id = pasted_source_id(conn)
    # An empty url is fine: the schema allows it, the UI hides the link, and
    # the dedup key falls back to title+company+city so pasting the same job
    # twice reopens the first one instead of creating a duplicate.
    url = (fields.get("url") or "").strip()
    job = norm.build_job(
        PASTED_SOURCE,
        {"external_id": None, "url": url},
        src_id,
        title=title,
        company=company,
        location=(fields.get("location") or "").strip(),
        body=body,
        posted=fields.get("posted_at") or datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        url=url,
        employment_type=(fields.get("employment_type") or "").strip() or None,
    )
    job_id, is_new = store.upsert_job(conn, job)
    if is_new:
        store.set_gate(conn, job_id, "passed", "you added this one by hand")
        store.save_reach(conn, job_id, reach_module.compute(job, cfg, prof))
    return {"job_id": job_id, "is_new": is_new, "title": title, "company": company}
