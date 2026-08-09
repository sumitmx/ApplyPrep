# ApplyPrep - handoff brief

Formerly named JobAgent. The product name was changed in the UI, docs, and the
FastAPI title; the Python package, CLI command, and working directory are
still called `jobagent` on purpose, since renaming those would break the
existing Claude Desktop MCP registration and every import in the codebase.

Read this first. It is the full context for the project. The build order is at
the bottom; start at the first unchecked item.

## What this is

A personal job discovery pipeline for one user, Alex, a Principal Architect
based in Lisbon looking for automation and AI architect roles in Europe,
primarily Germany and the Netherlands, requiring visa sponsorship.

It pulls postings from documented APIs and public ATS board endpoints into one
SQLite file. It is read only against every source. It never submits an
application.

## The single most important design constraint

**This codebase makes zero LLM calls. There is no API key anywhere in it.**

Scoring, CV tailoring and keyword judgement happen in Claude Desktop chat over
an MCP layer, paid for by an existing subscription. The Python package only
does deterministic work.

The rule for deciding where something belongs:

- a fact that code can compute -> goes in the package
- an opinion that needs judgement -> goes in the chat

Examples. Sponsorship stated in the ad is a fact, so `normalize.py` extracts
it. Whether this role is worth applying to is an opinion, so Claude decides it
in chat and writes the result back via `save_scores`.

If you find yourself about to add an `openai` or `anthropic` import to this
package, stop. That is the wrong layer.

## Two front doors, one brain

    React UI  -->  FastAPI (localhost)  -->  jobagent/  -->  jobs.db
    Claude    -->  MCP server (stdio)   -->  jobagent/  -->  jobs.db

Both shells call the same functions in `jobagent/`. Neither shell owns any
behaviour of its own. Keep it that way, or scoring a job in chat will not show
up in the browser.

There is deliberately no `/api/score` and no `/api/tailor`.

## Current state

Working and tested:

- `jobagent/config.py` - config loading, env override for Adzuna keys
- `jobagent/schema.sql` - full schema
- `jobagent/store.py` - all database access, `upsert_job` is idempotent on
  `dedup_key` and merges `source_ids` on repeat sightings
- `jobagent/normalize.py` - Arbeitnow payload to one job shape
- `jobagent/gate.py` - rules gate, pure functions
- `jobagent/pull.py` - orchestration, writes `run_log`
- `jobagent/adapters/aggregator/arbeitnow.py`
- `cli.py` - init, pull, list
- `tests/test_gate.py` - 5 passing

Not verified: the live Arbeitnow response shape. `from_arbeitnow` in
`normalize.py` guesses the payload keys. The first real `python cli.py pull`
may need a field mapping fix. Fix it against the actual response, do not guess
twice.

## Gate defaults, and why they are loose

The gate rejects only on: excluded junior titles, explicitly denied
sponsorship, and staleness past 45 days.

It does **not** reject on German language requirement, contract type, or
salary. Those are recorded on the job and feed the reachability score instead.

This is deliberate. A gate that kills on ambiguity loses roles silently and you
never find out. Tighten it in `config.yaml` once real data shows what is noise.
Three questions remain open and the defaults above stand in for them: German
level, per country salary floors, contract roles in or out.

## Two scores, not one

Every job gets **fit** and **reach**, stored separately in the `score` table.

- fit is merit: core technical 30, seniority and scope 20, domain 15,
  logistics 20, compensation 10, signal 5
- reach is whether it is landable: sponsorship, language, direct employer vs
  agency, freshness, Blue Card threshold

Do not blend them. A role can fit perfectly and be unreachable, and merging
the numbers hides which lever to pull. Most of reach is computable in Python,
so it belongs in `reach.py`, not in chat.

## Sources

In:

- Adzuna (key required, 1000 free calls a month, has salary data)
- Arbeitnow (keyless, publishes a visa sponsorship flag as structured data)
- Remotive, RemoteOK (keyless JSON)
- We Work Remotely (RSS)
- Greenhouse, Lever, Ashby, Workable public board JSON, one company token per
  call, driven by a user curated watchlist of 60 to 100 companies

Out, permanently:

- LinkedIn, Indeed, Glassdoor - login walls and terms of service
- Upwork, Freelancer - block programmatic access and ban accounts for it
- GitHub Jobs - dead since 2021

Do not add browser automation to reach any of these. That is what gets
accounts banned.

## Things that do not exist and should not be built

- **ATS score.** No applicant tracking system emits a score. The document
  module reports parse safety checks, which code can verify, and keyword
  coverage in three buckets: covered, fixable gap, real gap. Never a
  percentage.
- **Offer probability ranking.** Nothing in a job ad predicts an offer.
  Response rate by fit band is the real version and it gets more accurate as
  applications accumulate.
- **Auto apply.** Every ATS forbids it. The app tracks, the user submits.
- **An orchestrator agent class.** The user triggers runs when they want them.
  There is no scheduler.

## Master CV and the fabrication guard

`master.yaml` holds every experience bullet with an id and skill tags, plus a
tiered skills block:

- core, with years attached
- working, with context
- familiar, with honest context, for example "deployed to managed clusters,
  not operated them"

All three tiers render as keyword strings the ATS indexes. The labels are what
keep the user safe in a technical panel.

The document generator may only emit bullet ids that already exist in
`master.yaml`. Rewording is allowed, inventing is not. Enforce this in code,
not in a prompt.

## Build order

    [x] 1. skeleton, config, schema
    [x] 2. arbeitnow adapter end to end
    [x] 3. normalize and store
    [x] 4. gate
    [x] 5. remaining aggregator adapters: remotive, remoteok, wwr, adzuna
    [x] 6. ats board adapters: greenhouse, lever, ashby, workable
    [x] 7. dedup.py, three passes
    [x] 8. reach.py
    [x] 9. mcp server
    [x] 10. documents module
    [x] 11. fastapi and react ui

Notes on the next few:

**Step 5.** The fetch pattern is identical across sources, so most of the work
is one normalizer per source. Add each to `NORMALIZERS` in `normalize.py` and
`REGISTRY` in `pull.py`. Adzuna needs the free developer keys first, and it is
the only source with real salary data, so map `salary_min`, `salary_max` and
`salary_currency` properly there.

**Step 6.** Board endpoints take a company token, so add a `watchlist.yaml`
holding company name, ats kind and token. One HTTP call per company. Populate
the `company` table from it.

**Step 7.** Three passes in fixed order: exact URL, structural hash of title
plus company plus city, then fuzzy token set ratio above 90 using rapidfuzz.
This is the module to slow down on. Test it against real duplicates from a live
pull, not synthetic ones.

**Step 9.** FastMCP over stdio, about 15 lines per tool. Tools: `pull_jobs`,
`get_pending`, `save_scores`, `mark` (batch signature, so triaging fifteen jobs
is not fifteen approval prompts), `top_jobs`, `render_dashboard`. Write tools
return plain language summaries, not status codes, because a model reads them.

## House rules

- No comments in the code
- ASCII only, no unicode
- No emojis
- Pure functions where possible, especially in `gate.py` and `dedup.py`
- Every new module gets tests before moving to the next build step
- `jobs.db` is the only thing here that cannot be regenerated

## Start here

Run the tests, then `python cli.py pull` to see whether the Arbeitnow mapping
holds. Fix it if not. Then begin step 5.
