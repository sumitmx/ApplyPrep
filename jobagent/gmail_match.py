"""Turns a harvested Gmail message into a linked application and a guess at
what it means - never applied automatically. gmail_sync.run() only stores raw
emails against no application; this module is the second, offline pass that
tries to say *whose* application an email belongs to and what it implies, so
the candidate has something concrete to approve or dismiss.
"""
import re

from . import store

_SUFFIX = re.compile(
    r"\b(inc|incorporated|ltd|limited|llc|llp|gmbh|ag|bv|nv|plc|co|corp|"
    r"corporation|sa|srl|oy|ab|kg|holdings|group)\b\.?",
    re.I,
)

_REJECTED = [
    "unfortunately", "not moving forward", "not moving forward with",
    "will not be moving forward", "decided not to proceed", "not selected",
    "other candidates", "unable to offer you", "regret to inform",
    "not be progressing", "pursue other candidates",
]
_OFFER = [
    "pleased to offer", "excited to offer", "extend an offer",
    "job offer", "offer letter", "welcome to the team",
]
_INTERVIEW = [
    "invite you to interview", "schedule an interview", "interview with",
    "meet the team", "would like to interview", "next round",
]
_SCREENING = [
    "phone screen", "screening call", "online assessment", "coding challenge",
    "take-home", "technical assessment", "initial call",
]


def _text(*parts):
    return " ".join(p for p in parts if p).lower()


def classify(subject, snippet):
    """A guess at what the email means, checked most-specific first so a
    rejection that happens to mention "interview" (\"we won't be moving
    forward after your interview\") still reads as a rejection.

    Returns one of "offer", "rejected", "interview", "screening", or None for
    a plain acknowledgement with no signal worth surfacing.
    """
    blob = _text(subject, snippet)
    if any(term in blob for term in _OFFER):
        return "offer"
    if any(term in blob for term in _REJECTED):
        return "rejected"
    if any(term in blob for term in _INTERVIEW):
        return "interview"
    if any(term in blob for term in _SCREENING):
        return "screening"
    return None


def normalize_company(name):
    """Strip legal suffixes and punctuation so "Acme, Inc." and "acme"
    compare equal against a sender domain or email body."""
    text = _SUFFIX.sub(" ", (name or "").lower())
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def _company_token(normalized):
    """The one word worth matching on. A single short common word ("the",
    "co") would match almost anything, so a weak normalized name is skipped
    rather than guessed at."""
    words = [w for w in normalized.split() if len(w) >= 4]
    return words[0] if words else None


# Only these application stages are worth matching a reply against - nothing
# was ever sent for a "drafting" job, so an email can't be about it.
SENT_STATUSES = ("applied", "screening", "interview", "offer")


def find_application(conn, sender, sender_domain, subject, snippet):
    """The most likely open application this email is about, or None.

    Matching is deliberately simple and explainable - a normalized company
    name appearing in the sender's domain or in the message text - rather
    than fuzzy or AI-scored, since a wrong guess here would misattribute
    someone else's news to your application. When more than one open
    application shares that company, the most recently applied one wins.
    """
    blob = _text(sender_domain, subject, snippet)
    rows = conn.execute(
        "SELECT application.id AS application_id, application.applied_at,"
        " job.company_name FROM application JOIN job ON job.id = application.job_id"
        " WHERE application.status IN ({})".format(
            ",".join("?" for _ in SENT_STATUSES)
        ),
        SENT_STATUSES,
    ).fetchall()

    candidates = []
    for row in rows:
        token = _company_token(normalize_company(row["company_name"]))
        if token and token in blob:
            candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda r: r["applied_at"] or "", reverse=True)
    return candidates[0]["application_id"]


def run(conn):
    """Match and classify every email gmail_sync.run() stored but has not
    been linked yet. Safe to call repeatedly - only touches rows still
    sitting with application_id IS NULL."""
    matched = 0
    classified = 0
    for row in store.unmatched_application_emails(conn):
        application_id = find_application(
            conn, row["sender"], row["sender_domain"], row["subject"], row["snippet"]
        )
        if application_id is None:
            continue
        suggestion = classify(row["subject"], row["snippet"])
        store.link_application_email(conn, row["id"], application_id, suggestion)
        matched += 1
        if suggestion:
            classified += 1
    return {"matched": matched, "classified": classified}
