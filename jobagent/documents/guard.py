ACTIONS = ("kept", "rewrote", "dropped", "pulled")


class FabricationError(Exception):
    pass


def known_bullets(master):
    found = {}
    for role in (master or {}).get("experience") or []:
        for bullet in role.get("bullets") or []:
            if isinstance(bullet, dict) and bullet.get("id"):
                found[str(bullet["id"])] = {
                    "text": bullet.get("text", ""),
                    "company": role.get("company"),
                    "skills": bullet.get("skills") or [],
                }
    for project in (master or {}).get("projects") or []:
        if project.get("id"):
            found[str(project["id"])] = {
                "text": project.get("text", ""),
                "company": project.get("name"),
                "skills": project.get("skills") or [],
            }
    return found


def check(changes, master):
    allowed = known_bullets(master)
    if not allowed:
        raise FabricationError("master.yaml has no bullets to draw from.")

    invented = []
    bad_action = []
    seen = set()
    clean = []

    for change in changes or []:
        bullet_id = str(change.get("id") or "").strip()
        action = str(change.get("action") or "").strip().lower()
        if bullet_id not in allowed:
            invented.append(bullet_id or "(missing id)")
            continue
        if action not in ACTIONS:
            bad_action.append(bullet_id + " -> " + (action or "(missing)"))
            continue
        if bullet_id in seen:
            continue
        seen.add(bullet_id)
        original = allowed[bullet_id]["text"]
        text = (change.get("text") or "").strip() or original
        clean.append({
            "id": bullet_id,
            "action": action,
            "company": allowed[bullet_id]["company"],
            "was": original if action == "rewrote" else None,
            "text": text,
            "reason": (change.get("reason") or "").strip() or None,
        })

    if invented:
        raise FabricationError(
            "Rejected. These bullet ids are not in master.yaml, so they were "
            "invented: " + ", ".join(sorted(set(invented)))
        )
    if bad_action:
        raise FabricationError(
            "Rejected. Unknown action for: " + ", ".join(bad_action)
            + ". Allowed actions are " + ", ".join(ACTIONS) + "."
        )
    if not clean:
        raise FabricationError("Claude returned no usable changes.")
    return clean


def selected_text(changes):
    return " ".join(
        c["text"] for c in changes if c["action"] in ("kept", "rewrote", "pulled")
    )
