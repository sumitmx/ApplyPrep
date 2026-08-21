import argparse
import json

from jobagent import config, dedup, gmail_sync, pull, store, watchlist
from jobagent.gmail import auth as gmail_auth


def main():
    parser = argparse.ArgumentParser(prog="jobagent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_pull = sub.add_parser("pull")
    p_pull.add_argument("--countries", default=None)
    p_pull.add_argument("--since-days", type=int, default=None)
    p_pull.add_argument("--only", default=None)

    sub.add_parser("regate")
    sub.add_parser("rebuild")
    sub.add_parser("reach")
    sub.add_parser("watchlist")

    p_dedup = sub.add_parser("dedup")
    p_dedup.add_argument("--apply", action="store_true")
    p_dedup.add_argument("--threshold", type=int, default=dedup.THRESHOLD)
    p_dedup.add_argument("--limit", type=int, default=25)

    p_prune = sub.add_parser("prune")
    p_prune.add_argument("--days", type=int, default=7)
    p_prune.add_argument("--apply", action="store_true")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.add_argument("--reload", action="store_true")

    sub.add_parser("gmail-auth")

    p_gmail_sync = sub.add_parser("gmail-sync")
    p_gmail_sync.add_argument("--days", type=int, default=None)

    p_list = sub.add_parser("list")
    p_list.add_argument("--gate", default="passed")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--why", action="store_true")

    args = parser.parse_args()
    cfg = config.load()
    conn = store.connect(cfg["db_path"])

    if args.cmd == "init":
        store.init(conn)
        print("schema created at " + cfg["db_path"])
        return

    store.init(conn)

    if args.cmd == "pull":
        countries = args.countries.split(",") if args.countries else None
        only = args.only.split(",") if args.only else None
        result = pull.run(conn, cfg, countries, args.since_days, only)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "reach":
        result = pull.recompute_reach(conn, cfg)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "watchlist":
        companies = pull.sync_watchlist(conn, cfg)
        grouped = watchlist.by_kind(companies)
        for kind in sorted(grouped):
            names = ", ".join(sorted(c["name"] for c in grouped[kind]))
            print(kind.ljust(11), str(len(grouped[kind])).rjust(3), names)
        print(str(len(companies)) + " companies in the watchlist")
        return

    if args.cmd == "dedup":
        found = dedup.find(conn, args.threshold)
        for name, groups in found["passes"].items():
            print(name.ljust(11), str(len(groups)).rjust(4), "groups")
        combined = found["groups"]
        print("combined".ljust(11), str(len(combined)).rjust(4), "groups")
        if not args.apply:
            for entry in dedup.describe(conn, combined[: args.limit]):
                print("")
                print("keep " + str(entry["keep"]))
                for member in entry["members"]:
                    mark = "  keep " if member["id"] == entry["keep"] else "  drop "
                    print(
                        mark + str(member["id"]).rjust(5),
                        (member["company_name"] or "")[:20].ljust(22),
                        (member["title"] or "")[:46],
                    )
            print("")
            print("dry run, nothing changed. add --apply to merge these")
            return
        result = dedup.apply(conn, combined)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "prune":
        result = pull.prune(conn, args.days, apply=args.apply)
        print(json.dumps(result, indent=2))
        if not args.apply:
            print("")
            print("dry run, nothing changed. add --apply to delete these")
        return

    if args.cmd == "rebuild":
        result = pull.rebuild(conn, cfg)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "regate":
        result = pull.regate(conn, cfg)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "gmail-auth":
        gcfg = cfg.get("gmail") or {}
        try:
            record = gmail_auth.connect(conn, gcfg.get("client_secret_path", "gmail_client_secret.json"))
        except gmail_auth.GmailAuthError as exc:
            print("Could not connect: " + str(exc))
            raise SystemExit(1)
        print("Connected as " + (record.get("account_email") or "unknown account"))
        return

    if args.cmd == "gmail-sync":
        gcfg = dict(cfg.get("gmail") or {})
        if args.days is not None:
            gcfg["lookback_days"] = args.days
        cfg = dict(cfg, gmail=gcfg)
        result = gmail_sync.run(conn, cfg)
        print(json.dumps(result, indent=2))
        return

    if args.cmd == "serve":
        from jobagent import api

        conn.close()
        api.serve(
            cfg,
            port=args.port,
            open_browser=not args.no_browser,
            reload=args.reload,
        )
        return

    if args.cmd == "list":
        rows = store.jobs_by_gate(conn, args.gate, args.limit)
        for row in rows:
            line = [
                str(row["id"]).rjust(4),
                row["sponsorship_status"].ljust(10),
                (row["company_name"] or "")[:22].ljust(24),
                (row["title"] or "")[:52],
            ]
            if args.why:
                line.append("| " + (row["gate_reason"] or "passed"))
            print(*line)
        print(str(len(rows)) + " jobs")


if __name__ == "__main__":
    main()
