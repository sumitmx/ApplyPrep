PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS company (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    ats_kind    TEXT,
    ats_token   TEXT,
    watched     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raw_posting (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES source(id),
    external_id TEXT,
    url         TEXT,
    payload     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    run_id      INTEGER REFERENCES run_log(id)
);

CREATE INDEX IF NOT EXISTS ix_raw_source_ext ON raw_posting(source_id, external_id);

CREATE TABLE IF NOT EXISTS job (
    id                  INTEGER PRIMARY KEY,
    dedup_key           TEXT NOT NULL UNIQUE,
    title               TEXT NOT NULL,
    company_id          INTEGER REFERENCES company(id),
    company_name        TEXT NOT NULL,
    country             TEXT,
    city                TEXT,
    remote              TEXT,
    employment_type     TEXT,
    posted_at           TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    url                 TEXT NOT NULL,
    description         TEXT,
    salary_min          INTEGER,
    salary_max          INTEGER,
    salary_currency     TEXT,
    sponsorship_status  TEXT NOT NULL DEFAULT 'unknown',
    language_required   TEXT,
    via_agency          INTEGER NOT NULL DEFAULT 0,
    source_ids          TEXT NOT NULL,
    gate_status         TEXT NOT NULL DEFAULT 'pending',
    gate_reason         TEXT,
    status              TEXT NOT NULL DEFAULT 'new'
);

CREATE INDEX IF NOT EXISTS ix_job_gate ON job(gate_status);
CREATE INDEX IF NOT EXISTS ix_job_status ON job(status);
CREATE INDEX IF NOT EXISTS ix_job_country ON job(country);

CREATE TABLE IF NOT EXISTS score (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES job(id),
    profile_version TEXT NOT NULL,
    rubric_version  TEXT NOT NULL,
    model           TEXT,
    fit             INTEGER NOT NULL,
    reach           INTEGER NOT NULL,
    dimensions      TEXT,
    rationale       TEXT,
    scored_at       TEXT NOT NULL,
    ats_score       INTEGER,
    offer_probability INTEGER,
    estimate_note   TEXT,
    UNIQUE (job_id, profile_version, rubric_version)
);

CREATE INDEX IF NOT EXISTS ix_score_job ON score(job_id);

CREATE TABLE IF NOT EXISTS job_reach (
    job_id      INTEGER PRIMARY KEY REFERENCES job(id),
    reach       INTEGER NOT NULL,
    base        INTEGER NOT NULL,
    factor      REAL NOT NULL,
    sponsorship TEXT,
    facts       TEXT,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL UNIQUE REFERENCES job(id),
    status          TEXT NOT NULL DEFAULT 'drafting',
    applied_at      TEXT,
    next_action     TEXT,
    next_action_at  TEXT
);

CREATE TABLE IF NOT EXISTS application_event (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id),
    event           TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES job(id),
    kind            TEXT NOT NULL,
    path            TEXT NOT NULL,
    master_version  TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setting (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_chat (
    job_id      INTEGER PRIMARY KEY REFERENCES job(id),
    messages    TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    countries       TEXT,
    since_days      INTEGER,
    raw_count       INTEGER DEFAULT 0,
    new_count       INTEGER DEFAULT 0,
    detail          TEXT
);

CREATE TABLE IF NOT EXISTS application_email (
    id                INTEGER PRIMARY KEY,
    application_id    INTEGER REFERENCES application(id),
    gmail_message_id  TEXT NOT NULL UNIQUE,
    gmail_thread_id   TEXT,
    subject           TEXT,
    sender            TEXT,
    sender_domain     TEXT,
    snippet           TEXT,
    received_at       TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_application_email_app ON application_email(application_id);

CREATE TABLE IF NOT EXISTS gmail_sync_log (
    id                 INTEGER PRIMARY KEY,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    messages_scanned   INTEGER DEFAULT 0,
    stored_count       INTEGER DEFAULT 0,
    detail             TEXT
);
