import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


ADDED_COLUMNS = {
    "score": [
        ("ats_score", "INTEGER"),
        ("offer_probability", "INTEGER"),
        ("estimate_note", "TEXT"),
    ],
    "document": [
        ("body", "TEXT"),
        ("payload", "TEXT"),
        ("word_count", "INTEGER"),
        ("accepted", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def init(conn):
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    migrate(conn)


def migrate(conn):
    applied = []
    conn.execute(
        "CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    for table, columns in ADDED_COLUMNS.items():
        cur = conn.execute("PRAGMA table_info(" + table + ")")
        existing = {r["name"] for r in cur.fetchall()}
        for name, kind in columns:
            if name not in existing:
                conn.execute(
                    "ALTER TABLE " + table + " ADD COLUMN " + name + " " + kind
                )
                applied.append(table + "." + name)
    conn.commit()
    return applied


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def source_id(conn, name, kind):
    cur = conn.execute("SELECT id FROM source WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO source (name, kind) VALUES (?, ?)", (name, kind)
    )
    conn.commit()
    return cur.lastrowid


def start_run(conn, countries, since_days):
    cur = conn.execute(
        "INSERT INTO run_log (started_at, countries, since_days) VALUES (?, ?, ?)",
        (now(), ",".join(countries), since_days),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, raw_count, new_count, detail):
    conn.execute(
        "UPDATE run_log SET finished_at = ?, raw_count = ?, new_count = ?, detail = ? WHERE id = ?",
        (now(), raw_count, new_count, json.dumps(detail), run_id),
    )
    conn.commit()


def raw_keys(conn, src_id):
    seen = set()
    for row in conn.execute(
        "SELECT DISTINCT external_id, url FROM raw_posting WHERE source_id = ?",
        (src_id,),
    ):
        seen.add(row["external_id"] or row["url"])
    seen.discard(None)
    return seen


def save_raw(conn, run_id, src_id, postings, skip_known=True):
    known = raw_keys(conn, src_id) if skip_known else set()
    rows = []
    for posting in postings:
        key = posting.get("external_id") or posting.get("url")
        if skip_known and key and key in known:
            continue
        if key:
            known.add(key)
        rows.append(
            (
                src_id,
                posting.get("external_id"),
                posting.get("url"),
                json.dumps(posting["payload"]),
                now(),
                run_id,
            )
        )
    conn.executemany(
        "INSERT INTO raw_posting (source_id, external_id, url, payload, fetched_at, run_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_job(conn, job):
    cur = conn.execute("SELECT id, source_ids FROM job WHERE dedup_key = ?", (job["dedup_key"],))
    row = cur.fetchone()
    stamp = now()
    if row:
        known = set(json.loads(row["source_ids"]))
        known.update(job["source_ids"])
        conn.execute(
            "UPDATE job SET last_seen_at = ?, source_ids = ? WHERE id = ?",
            (stamp, json.dumps(sorted(known)), row["id"]),
        )
        conn.commit()
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO job (dedup_key, title, company_name, country, city, remote,"
        " employment_type, posted_at, first_seen_at, last_seen_at, url, description,"
        " salary_min, salary_max, salary_currency, sponsorship_status, language_required,"
        " via_agency, source_ids)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job["dedup_key"],
            job["title"],
            job["company_name"],
            job.get("country"),
            job.get("city"),
            job.get("remote"),
            job.get("employment_type"),
            job.get("posted_at"),
            stamp,
            stamp,
            job["url"],
            job.get("description"),
            job.get("salary_min"),
            job.get("salary_max"),
            job.get("salary_currency"),
            job.get("sponsorship_status", "unknown"),
            job.get("language_required"),
            1 if job.get("via_agency") else 0,
            json.dumps(sorted(job["source_ids"])),
        ),
    )
    conn.commit()
    return cur.lastrowid, True


def jobs_by_gate(conn, gate_status, limit=50):
    cur = conn.execute(
        "SELECT * FROM job WHERE gate_status = ? ORDER BY posted_at DESC LIMIT ?",
        (gate_status, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def set_gate(conn, job_id, status, reason):
    conn.execute(
        "UPDATE job SET gate_status = ?, gate_reason = ? WHERE id = ?",
        (status, reason, job_id),
    )
    conn.commit()


def get_score(conn, job_id):
    row = conn.execute(
        "SELECT * FROM score WHERE job_id = ? ORDER BY scored_at DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    return dict(row) if row else None


def upsert_score(conn, score):
    conn.execute(
        "INSERT INTO score (job_id, profile_version, rubric_version, model, fit,"
        " reach, dimensions, rationale, scored_at, ats_score, offer_probability,"
        " estimate_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (job_id, profile_version, rubric_version) DO UPDATE SET"
        " model = excluded.model, fit = excluded.fit, reach = excluded.reach,"
        " dimensions = excluded.dimensions, rationale = excluded.rationale,"
        " scored_at = excluded.scored_at, ats_score = excluded.ats_score,"
        " offer_probability = excluded.offer_probability,"
        " estimate_note = excluded.estimate_note",
        (
            score["job_id"],
            score.get("profile_version", "v1"),
            score.get("rubric_version", "v1"),
            score.get("model"),
            score["fit"],
            score["reach"],
            json.dumps(score["dimensions"]) if score.get("dimensions") else None,
            score.get("rationale"),
            now(),
            score.get("ats_score"),
            score.get("offer_probability"),
            score.get("estimate_note"),
        ),
    )
    conn.commit()


def save_document(conn, job_id, kind, body=None, payload=None, word_count=None,
                  master_version=None, path=None):
    conn.execute("DELETE FROM document WHERE job_id = ? AND kind = ?", (job_id, kind))
    cur = conn.execute(
        "INSERT INTO document (job_id, kind, path, master_version, created_at,"
        " body, payload, word_count, accepted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (
            job_id, kind, path or "", master_version, now(), body,
            json.dumps(payload) if payload is not None else None, word_count,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_document(conn, job_id, kind):
    cur = conn.execute(
        "SELECT * FROM document WHERE job_id = ? AND kind = ?"
        " ORDER BY created_at DESC LIMIT 1",
        (job_id, kind),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def start_application(conn, job_id):
    conn.execute(
        "INSERT INTO application (job_id, status) VALUES (?, 'drafting')"
        " ON CONFLICT (job_id) DO NOTHING",
        (job_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, status, applied_at FROM application WHERE job_id = ?", (job_id,)
    ).fetchone()
    return dict(row) if row else None


def accept_document(conn, document_id, accepted=True):
    conn.execute(
        "UPDATE document SET accepted = ? WHERE id = ?",
        (1 if accepted else 0, document_id),
    )
    conn.commit()


def upsert_company(conn, name, slug, ats_kind=None, ats_token=None, watched=1):
    cur = conn.execute("SELECT id FROM company WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE company SET name = ?, ats_kind = ?, ats_token = ?, watched = ?"
            " WHERE id = ?",
            (name, ats_kind, ats_token, watched, row["id"]),
        )
        conn.commit()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO company (name, slug, ats_kind, ats_token, watched)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, slug, ats_kind, ats_token, watched),
    )
    conn.commit()
    return cur.lastrowid


def company_ids(conn):
    return {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM company")}


def set_job_company(conn, job_id, company_id):
    conn.execute("UPDATE job SET company_id = ? WHERE id = ?", (company_id, job_id))
    conn.commit()


def save_reach(conn, job_id, data):
    conn.execute(
        "INSERT INTO job_reach (job_id, reach, base, factor, sponsorship, facts,"
        " computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (job_id) DO UPDATE SET reach = excluded.reach,"
        " base = excluded.base, factor = excluded.factor,"
        " sponsorship = excluded.sponsorship, facts = excluded.facts,"
        " computed_at = excluded.computed_at",
        (
            job_id, data["reach"], data["base"], data["factor"],
            data.get("sponsorship"), json.dumps(data.get("facts")), now(),
        ),
    )
    conn.commit()


def save_reach_many(conn, pairs):
    stamp = now()
    conn.executemany(
        "INSERT INTO job_reach (job_id, reach, base, factor, sponsorship, facts,"
        " computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (job_id) DO UPDATE SET reach = excluded.reach,"
        " base = excluded.base, factor = excluded.factor,"
        " sponsorship = excluded.sponsorship, facts = excluded.facts,"
        " computed_at = excluded.computed_at",
        [
            (
                job_id, data["reach"], data["base"], data["factor"],
                data.get("sponsorship"), json.dumps(data.get("facts")), stamp,
            )
            for job_id, data in pairs
        ],
    )
    conn.commit()
    return len(pairs)


def get_reach(conn, job_id):
    row = conn.execute("SELECT * FROM job_reach WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def all_jobs(conn):
    cur = conn.execute("SELECT * FROM job ORDER BY id")
    return [dict(r) for r in cur.fetchall()]


def set_gate_many(conn, updates):
    conn.executemany(
        "UPDATE job SET gate_status = ?, gate_reason = ? WHERE id = ?", updates
    )
    conn.commit()
    return len(updates)
