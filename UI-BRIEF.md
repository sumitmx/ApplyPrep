# UI build brief

Open `design/ui-mockup.html` in a browser before writing anything. It is the
visual reference and the source of truth for layout, palette and screen
content. Every colour, spacing value and component pattern you need is in its
stylesheet. Match it rather than reinventing it.

## Stack

- FastAPI serving JSON, uvicorn, bound to 127.0.0.1 only
- React with Vite, plain CSS matching the mockup, no component library
- The React build output is served as static files by FastAPI so there is one
  process and one URL
- Default port 8756, overridable in `config.yaml`

No authentication. It is one user on one laptop, never exposed.

## The hard constraint

The UI does not call any model and there is no API key in this layer.

FastAPI is a thin shell over the existing `jobagent/` package. If a route needs
logic that is not already in `jobagent/`, add it to `jobagent/` and call it,
do not put it in the route handler. The MCP server calls the same functions,
and behaviour that lives in only one shell will silently diverge.

Routes to build:

    GET  /api/dashboard              counts, response rate by band, next actions
    GET  /api/sources               last run per source, dedup pass counts
    GET  /api/jobs                  filters: gate, country, min_fit, status
    GET  /api/jobs/{id}             detail with score dimensions and skill match
    POST /api/jobs/{id}/mark        shortlist, hide, reject, with reason
    GET  /api/applications          funnel counts plus table rows
    POST /api/applications/{id}     status change, logs an application_event
    GET  /api/master-cv             tiered skills, pending classifications
    GET  /api/documents/{job_id}    rendered docx paths for a job
    POST /api/pull                  triggers a source run, returns run summary

Deliberately absent: no `/api/score`, no `/api/tailor`, no
`/api/keywords/classify`. Those need judgement and happen in Claude chat over
MCP. The UI displays their stored results and nothing more.

## Screens

Eight, matching the mockup's sidebar order. Build them in this order because
each one is useful before the next exists.

**1. Dashboard.** Metric cards: new after dedup, passed gate, awaiting score,
shortlisted, applied this month. Response rate by fit band as two bars, 80+
and 60 to 79. Next actions list. All from `/api/dashboard`.

**2. Jobs.** The list. Each row shows title, company, location, posted age,
badges, and two score numbers side by side. Whole row is a link to
`/jobs/{id}`, a real route so back button and bookmarking work. Shortlist and
hide buttons on the row must not navigate, or triaging fifteen jobs becomes
fifteen round trips. Filters for gate status, country, minimum fit.

**3. Job detail.** Two panels side by side, fit with its six weighted
dimensions as bars, reach as a checklist of facts. Below, the skill match
panel split into matched from core, matched from working, matched from
familiar, and genuine gap. Add previous and next arrows to walk the shortlist
without returning to the list.

**4. Discover.** Per source: name, job count, status pill. Dedup pass counts
below. Read only view of the last `run_log` row. The pull button posts to
`/api/pull`.

**5. Applications.** Funnel counts as cards, then a table with role, company,
fit, status, sent date, next action. Status changes post back and append an
`application_event`.

**6. Master CV.** The three skill tiers rendered as chips with their context
labels. Pending keyword classifications listed but not editable here, the user
classifies them in chat.

**7. Tailor CV.** Read only in this version. Shows the stored bullet diff for a
job, the parse safety checklist, and keyword coverage as three counts. The
diff itself is generated in chat and saved; this screen displays it and offers
a download.

**8. Cover letter.** Read only. Stored draft text plus word count and download.

## Two things not to build

**No score dial or percentage anywhere.** Keyword coverage renders as three
counts, covered, fixable gap, real gap. Parse safety renders as pass or fail
per check. No applicant tracking system emits a score and a green ring would
be a fabricated number that quietly changes which jobs the user chases.

**No blended match percentage.** Fit and reach stay as two numbers, always
adjacent, never averaged. That separation is the point of the design.

## Behaviour details worth getting right

- Empty states matter more than usual here. A fresh database has no jobs, no
  scores and no applications. Every screen needs a sensible empty state that
  says what to do next, not a spinner or a blank panel.
- Jobs awaiting a score should be visibly distinct from scored ones, since
  scoring happens elsewhere and the user needs to know what is pending.
- The pull button is slow, ten to forty seconds. Show per source progress if
  the endpoint streams, otherwise a clear pending state and a summary on
  completion.
- Dates as relative age, "4 days ago", not timestamps. Staleness is a signal
  the user acts on.

## Definition of done

`python cli.py serve` starts uvicorn and opens the browser. All eight screens
render from real data in `jobs.db`. Marking a job in the UI is visible in the
next chat session over MCP, and a score written from chat appears on refresh.
No API key required to run any of it.
