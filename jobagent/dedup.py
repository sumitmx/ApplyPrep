import json

from rapidfuzz import fuzz

from . import normalize as norm

THRESHOLD = 90

LEVEL_WORDS = {
    "intern", "internship", "junior", "jr", "graduate", "entry",
    "mid", "senior", "sr", "staff", "principal", "lead", "head",
    "director", "vp", "chief", "manager", "manager", "trainee",
    "working", "student", "werkstudent", "praktikum", "i", "ii", "iii", "iv",
}

FIELDS = (
    "SELECT id, dedup_key, title, company_name, city, country, url,"
    " first_seen_at, posted_at, source_ids FROM job ORDER BY id"
)


def rows(conn):
    return [dict(r) for r in conn.execute(FIELDS)]


def _grouped(pairs):
    groups = {}
    for key, job_id in pairs:
        if not key:
            continue
        groups.setdefault(key, []).append(job_id)
    return [sorted(v) for v in groups.values() if len(v) > 1]


def pass_url(items):
    return _grouped([(norm.canonical_url(r.get("url")), r["id"]) for r in items])


def pass_structural(items):
    return _grouped(
        [
            (
                norm.structural_key(r.get("title"), r.get("company_name"), r.get("city")),
                r["id"],
            )
            for r in items
        ]
    )


def levels(title):
    words = set(norm.slugify(title).split("-"))
    return words & LEVEL_WORDS


def prepare(items):
    return [
        {
            "id": row["id"],
            "title": row.get("title") or "",
            "company": norm.slugify(row.get("company_name")),
            "city": norm.slugify(row.get("city") or ""),
            "levels": levels(row.get("title")),
        }
        for row in items
    ]


def comparable(left, right):
    if left["company"] != right["company"]:
        return False
    if left["city"] and right["city"] and left["city"] != right["city"]:
        return False
    return left["levels"] == right["levels"]


def pass_fuzzy(items, threshold=THRESHOLD):
    buckets = {}
    for row in prepare(items):
        if row["company"]:
            buckets.setdefault(row["company"], []).append(row)

    found = []
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        taken = set()
        for index, left in enumerate(bucket):
            if left["id"] in taken:
                continue
            group = [left["id"]]
            for right in bucket[index + 1:]:
                if right["id"] in taken or not comparable(left, right):
                    continue
                if fuzz.token_set_ratio(left["title"], right["title"]) >= threshold:
                    group.append(right["id"])
                    taken.add(right["id"])
            if len(group) > 1:
                taken.add(left["id"])
                found.append(sorted(group))
    return found


def merge_groups(groups):
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for group in groups:
        first = group[0]
        for other in group[1:]:
            a, b = find(first), find(other)
            if a != b:
                parent[max(a, b)] = min(a, b)

    clusters = {}
    for node in list(parent):
        clusters.setdefault(find(node), set()).add(node)
    return [sorted(v) for v in clusters.values() if len(v) > 1]


def find(conn, threshold=THRESHOLD):
    items = rows(conn)
    by_pass = {
        "url": pass_url(items),
        "structural": pass_structural(items),
        "fuzzy": pass_fuzzy(items, threshold),
    }
    combined = merge_groups(by_pass["url"] + by_pass["structural"] + by_pass["fuzzy"])
    return {"passes": by_pass, "groups": combined, "total_jobs": len(items)}


def summary(conn, threshold=THRESHOLD):
    found = find(conn, threshold)
    return {
        "total_jobs": found["total_jobs"],
        "exact_url": len(found["passes"]["url"]),
        "same_role": len(found["passes"]["structural"]),
        "reworded": len(found["passes"]["fuzzy"]),
        "groups": len(found["groups"]),
        "duplicate_jobs": sum(len(g) - 1 for g in found["groups"]),
    }


def references(conn, table, job_ids):
    if not job_ids:
        return {}
    marks = ",".join("?" for _ in job_ids)
    out = {}
    for row in conn.execute(
        "SELECT job_id, COUNT(*) AS n FROM " + table +
        " WHERE job_id IN (" + marks + ") GROUP BY job_id",
        list(job_ids),
    ):
        out[row["job_id"]] = row["n"]
    return out


def pick_survivor(conn, group):
    scores = references(conn, "score", group)
    apps = references(conn, "application", group)
    docs = references(conn, "document", group)
    detail = {r["id"]: r for r in conn.execute(
        "SELECT id, first_seen_at FROM job WHERE id IN (" +
        ",".join("?" for _ in group) + ")", list(group)
    )}

    def rank(job_id):
        return (
            -(scores.get(job_id, 0) + apps.get(job_id, 0) + docs.get(job_id, 0)),
            str(detail.get(job_id, {})["first_seen_at"] if job_id in detail else ""),
            job_id,
        )

    return sorted(group, key=rank)[0]


def describe(conn, groups):
    out = []
    for group in groups:
        marks = ",".join("?" for _ in group)
        members = [
            dict(r) for r in conn.execute(
                "SELECT id, title, company_name, city, url FROM job WHERE id IN ("
                + marks + ") ORDER BY id", list(group)
            )
        ]
        out.append({"keep": pick_survivor(conn, group), "members": members})
    return out


def apply(conn, groups):
    merged = 0
    removed = []
    blocked = []

    for group in groups:
        keep = pick_survivor(conn, group)
        others = [i for i in group if i != keep]
        apps = references(conn, "application", group)
        if len([i for i in group if apps.get(i)]) > 1:
            blocked.append({"group": group, "why": "more than one application row"})
            continue

        known = set()
        for row in conn.execute(
            "SELECT source_ids FROM job WHERE id IN (" +
            ",".join("?" for _ in group) + ")", list(group)
        ):
            try:
                known.update(json.loads(row["source_ids"]))
            except (TypeError, ValueError):
                continue

        for other in others:
            conn.execute("UPDATE document SET job_id = ? WHERE job_id = ?", (keep, other))
            conn.execute(
                "UPDATE OR IGNORE application SET job_id = ? WHERE job_id = ?", (keep, other)
            )
            conn.execute("DELETE FROM application WHERE job_id = ?", (other,))
            conn.execute(
                "UPDATE OR IGNORE score SET job_id = ? WHERE job_id = ?", (keep, other)
            )
            conn.execute("DELETE FROM score WHERE job_id = ?", (other,))
            conn.execute("DELETE FROM job_reach WHERE job_id = ?", (other,))
            conn.execute("DELETE FROM job WHERE id = ?", (other,))
            removed.append(other)

        conn.execute(
            "UPDATE job SET source_ids = ? WHERE id = ?",
            (json.dumps(sorted(known)), keep),
        )
        merged += 1

    conn.commit()
    return {"groups_merged": merged, "jobs_removed": len(removed),
            "removed_ids": removed, "blocked": blocked}
