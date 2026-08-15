import hashlib
import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

COUNTRY_NAMES = {
    "germany": "DE", "deutschland": "DE",
    "netherlands": "NL", "nederland": "NL", "holland": "NL",
    "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB",
    "austria": "AT", "osterreich": "AT",
    "switzerland": "CH", "schweiz": "CH",
    "ireland": "IE", "france": "FR", "spain": "ES", "italy": "IT",
    "sweden": "SE", "denmark": "DK", "norway": "NO", "finland": "FI",
    "poland": "PL", "portugal": "PT", "belgium": "BE", "belgie": "BE",
    "luxembourg": "LU", "czechia": "CZ", "czech republic": "CZ",
}

COUNTRY_CODES = {
    "de", "nl", "gb", "uk", "at", "ch", "ie", "fr", "es", "it",
    "se", "dk", "no", "fi", "pl", "pt", "be", "lu", "cz",
}

CITY_COUNTRY = {
    "berlin": "DE", "munich": "DE", "munchen": "DE", "hamburg": "DE",
    "cologne": "DE", "koln": "DE", "stuttgart": "DE", "dusseldorf": "DE",
    "frankfurt": "DE", "frankfurt am main": "DE", "bremen": "DE",
    "nuremberg": "DE", "nurnberg": "DE", "leipzig": "DE", "heidelberg": "DE",
    "mulheim": "DE", "mannheim": "DE", "bielefeld": "DE", "gutersloh": "DE",
    "erfurt": "DE", "karlsruhe": "DE", "hagen": "DE", "kaarst": "DE",
    "dresden": "DE", "hannover": "DE", "essen": "DE", "dortmund": "DE",
    "bonn": "DE", "augsburg": "DE", "wiesbaden": "DE", "munster": "DE",
    "aachen": "DE", "kiel": "DE", "freiburg": "DE", "regensburg": "DE",
    "darmstadt": "DE", "potsdam": "DE", "ulm": "DE", "wurzburg": "DE",
    "reinbek": "DE", "gummersbach": "DE", "ehingen": "DE", "nordheim": "DE",
    "schwabmunchen": "DE", "saarbrucken": "DE", "chemnitz": "DE",
    "magdeburg": "DE", "braunschweig": "DE", "jena": "DE", "kassel": "DE",
    "paderborn": "DE", "osnabruck": "DE", "oldenburg": "DE", "lubeck": "DE",
    "deggenhausertal": "DE", "ingolstadt": "DE", "wolfsburg": "DE",
    "amsterdam": "NL", "rotterdam": "NL", "utrecht": "NL", "eindhoven": "NL",
    "the hague": "NL", "den haag": "NL", "groningen": "NL", "delft": "NL",
    "haarlem": "NL", "tilburg": "NL", "breda": "NL", "nijmegen": "NL",
    "arnhem": "NL", "leiden": "NL", "maastricht": "NL", "almere": "NL",
    "london": "GB", "manchester": "GB", "birmingham": "GB", "edinburgh": "GB",
    "glasgow": "GB", "bristol": "GB", "leeds": "GB", "cambridge": "GB",
    "oxford": "GB", "liverpool": "GB", "sheffield": "GB", "newcastle": "GB",
    "cardiff": "GB", "belfast": "GB", "brighton": "GB", "reading": "GB",
    "vienna": "AT", "wien": "AT", "graz": "AT", "linz": "AT",
    "zurich": "CH", "geneva": "CH", "basel": "CH", "bern": "CH", "lausanne": "CH",
    "dublin": "IE", "cork": "IE", "galway": "IE",
    "paris": "FR", "lyon": "FR", "toulouse": "FR", "nantes": "FR",
    "madrid": "ES", "barcelona": "ES", "valencia": "ES",
    "milan": "IT", "rome": "IT", "turin": "IT",
    "stockholm": "SE", "gothenburg": "SE", "malmo": "SE",
    "copenhagen": "DK", "aarhus": "DK", "oslo": "NO", "helsinki": "FI",
    "warsaw": "PL", "krakow": "PL", "wroclaw": "PL", "prague": "CZ",
    "lisbon": "PT", "porto": "PT",
    "brussels": "BE", "antwerp": "BE", "ghent": "BE", "leuven": "BE",
    "luxembourg": "LU",
}

_SPLIT = re.compile(r"[,/|;]| - | or | and ")
_WORD = re.compile(r"[a-z]+")
_DE_POSTCODE = re.compile(r"\b\d{5}\b")
_DE_STREET = re.compile(r"(?:strasse|str\.|platz|allee|weg)\b")

AGENCY_HINTS = [
    "hays", "michael page", "robert half", "randstad", "adecco",
    "recruitment", "consulting gmbh", "staffing", "talent partner",
]

SPONSOR_YES = [
    "visa sponsorship", "we sponsor", "sponsorship available",
    "blue card", "relocation support", "visa support",
]

SPONSOR_NO = [
    "no visa sponsorship", "not able to sponsor", "cannot sponsor",
    "must have the right to work", "eu work permit required",
    "no sponsorship available",
]

_SPONSOR_FILLER = r"(?:currently|unfortunately|sadly|presently|immediately|generally|typically)"
_SPONSOR_GRANT_VERBS = r"(?:offer|provide|support|guarantee|give)\w*"

_SPONSOR_NEGATION = re.compile(
    r"(?:unable to|not able to|cannot|can't|won't|will not|do not|don't|"
    r"does not|doesn't|no longer able to)"
    r"(?:\s+" + _SPONSOR_FILLER + r")?\s+"
    r"(?:sponsor\w*|" + _SPONSOR_GRANT_VERBS +
    r"(?:\s+\w+){0,4}\s+(?:sponsor\w*|visa))"
)

GERMAN_HINTS = [
    "german language", "deutschkenntnisse", "fliessend deutsch",
    "german b2", "german c1", "sehr gute deutschkenntnisse",
]

EUROPE_HINTS = {
    "europe", "european", "europa", "emea", "eea", "eu", "schengen",
    "cet", "cest", "european union", "european timezones", "uk",
}

WORLDWIDE_HINTS = {
    "worldwide", "anywhere", "global", "globally", "international",
    "everywhere", "remote", "distributed",
}

OTHER_REGIONS = {
    "usa", "us", "united states", "america", "americas", "north america",
    "south america", "latam", "latin america", "canada", "brazil", "mexico",
    "argentina", "colombia", "chile", "peru", "india", "pakistan",
    "bangladesh", "sri lanka", "philippines", "indonesia", "vietnam",
    "thailand", "malaysia", "singapore", "china", "hong kong", "japan",
    "korea", "taiwan", "australia", "new zealand", "oceania", "apac",
    "asia", "asia pacific", "africa", "south africa", "nigeria", "kenya",
    "ghana", "egypt", "morocco", "israel", "turkey", "uae", "dubai",
    "saudi arabia", "qatar", "middle east", "russia",
}

ADZUNA_CURRENCY = {
    "de": "EUR", "nl": "EUR", "at": "EUR", "fr": "EUR", "es": "EUR",
    "it": "EUR", "ie": "EUR", "be": "EUR", "pt": "EUR", "lu": "EUR",
    "gb": "GBP", "ch": "CHF", "pl": "PLN", "se": "SEK", "dk": "DKK",
    "no": "NOK", "cz": "CZK",
}

_SCRIPTS = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BREAKS = re.compile(r"(?i)<br\s*/?>")
_LIST_ITEM = re.compile(r"(?i)<li[^>]*>")
_BLOCK_END = re.compile(r"(?i)</(p|div|li|h[1-6]|tr|ul|ol)>")
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")

SHARP_S = chr(223)
NBSP = chr(160)
_MOJIBAKE = re.compile(
    "[" + chr(194) + chr(195) + chr(226) + "][" + chr(128) + "-" + chr(191) + "]"
)


def fold(text):
    stripped = unicodedata.normalize("NFKD", (text or "").replace(SHARP_S, "ss"))
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower().strip()


def segments(location):
    return [s.strip() for s in _SPLIT.split(fold(location)) if s.strip()]


def phrases(location):
    words = _WORD.findall(fold(location))
    out = []
    for i, word in enumerate(words):
        out.append(word)
        if i + 1 < len(words):
            out.append(word + " " + words[i + 1])
        if i + 2 < len(words):
            out.append(word + " " + words[i + 1] + " " + words[i + 2])
    return out


def _lookup(location, table):
    for phrase in phrases(location):
        if phrase in table:
            return table[phrase]
    return None


def detect_country(location):
    if not (location or "").strip():
        return None
    named = _lookup(location, COUNTRY_NAMES)
    if named:
        return named
    parts = segments(location)
    if parts and parts[-1] in COUNTRY_CODES:
        code = parts[-1].upper()
        return "GB" if code == "UK" else code
    city = _lookup(location, CITY_COUNTRY)
    if city:
        return city
    if _DE_POSTCODE.search(location) or _DE_STREET.search(fold(location)):
        return "DE"
    return None


def detect_city(location):
    for phrase in phrases(location):
        if phrase in CITY_COUNTRY:
            return phrase.title()
    parts = segments(location)
    if parts and parts[0] not in COUNTRY_NAMES and "remote" not in parts[0]:
        return parts[0].title()
    return None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def dedup_key(title, company, city):
    raw = "|".join([slugify(title), slugify(company), slugify(city or "")])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def canonical_url(url):
    text = (url or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = text.split("#")[0].split("?")[0]
    return text.rstrip("/")


def structural_key(title, company, city):
    raw = "struct|" + "|".join([slugify(title), slugify(company), slugify(city or "")])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def stable_key(source_name, external_id, url, title=None, company=None, city=None):
    canonical = canonical_url(url)
    if canonical:
        raw = "url|" + canonical
    elif external_id:
        raw = "ext|" + str(source_name) + "|" + str(external_id)
    else:
        return structural_key(title, company, city)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def detect_sponsorship(text):
    low = (text or "").lower()
    for phrase in SPONSOR_NO:
        if phrase in low:
            return "denied"
    if _SPONSOR_NEGATION.search(low):
        return "denied"
    for phrase in SPONSOR_YES:
        if phrase in low:
            return "confirmed"
    return "unknown"


def detect_language(text):
    low = (text or "").lower()
    for phrase in GERMAN_HINTS:
        if phrase in low:
            return "de"
    return "en"


def detect_agency(company):
    low = (company or "").lower()
    return any(hint in low for hint in AGENCY_HINTS)


def repair_text(text):
    if not text or not _MOJIBAKE.search(text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def strip_html(text):
    if not text:
        return ""
    body = html.unescape(str(text))
    if "<" in body and ">" in body:
        body = _SCRIPTS.sub(" ", body)
        body = _BREAKS.sub("\n", body)
        body = _LIST_ITEM.sub("- ", body)
        body = _BLOCK_END.sub("\n", body)
        body = _TAGS.sub("", body)
        body = html.unescape(body)
    body = body.replace(NBSP, " ")
    body = _SPACES.sub(" ", body)
    body = _BLANKS.sub("\n\n", body)
    return "\n".join(line.strip() for line in body.split("\n")).strip()


def clean_line(text):
    return _SPACES.sub(" ", str(text or "").replace("\n", " ")).strip()


def parse_stamp(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_stamp(int(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def within_days(stamp, days):
    if not days:
        return True
    parsed = parse_stamp(stamp)
    if not parsed:
        return True
    return datetime.fromisoformat(parsed) >= datetime.now(timezone.utc) - timedelta(days=days)


def is_worldwide(location):
    return bool(set(phrases(location)) & WORLDWIDE_HINTS)


def region_allows(location, allow_unknown=True):
    if not (location or "").strip():
        return allow_unknown
    found = set(phrases(location))
    if found & EUROPE_HINTS:
        return True
    if detect_country(location):
        return True
    if found & OTHER_REGIONS:
        return False
    if found & WORLDWIDE_HINTS:
        return True
    return False


def build_job(source_name, raw, source_id, title, company, location, body,
              posted=None, url=None, employment_type=None, remote=None,
              salary_min=None, salary_max=None, salary_currency=None,
              sponsorship=None, extra=None):
    title = clean_line(title)
    company = clean_line(company)
    location = clean_line(location)
    body = repair_text(strip_html(body))
    country = detect_country(location)
    city = detect_city(location)
    if city and not country and is_worldwide(location):
        city = None
    url = url or raw.get("url")
    blob = " ".join([body, clean_line(extra), location])
    if remote is None:
        remote = "remote" if "remote" in fold(location) else "onsite"
    has_salary = bool(salary_min or salary_max)
    return {
        "dedup_key": stable_key(
            source_name, raw.get("external_id"), url, title, company, city
        ),
        "title": title,
        "company_name": company,
        "country": country,
        "city": city,
        "remote": remote,
        "employment_type": employment_type,
        "posted_at": parse_stamp(posted),
        "url": url,
        "description": body,
        "salary_min": salary_min if has_salary else None,
        "salary_max": salary_max if has_salary else None,
        "salary_currency": salary_currency if has_salary else None,
        "sponsorship_status": sponsorship or detect_sponsorship(blob),
        "language_required": detect_language(blob),
        "via_agency": detect_agency(company),
        "source_ids": [source_id],
    }


def from_arbeitnow(raw, source_id):
    row = raw["payload"]
    title = row.get("title", "")
    company = row.get("company_name", "")
    location = row.get("location", "") or ""
    city = detect_city(location)
    country = detect_country(location)
    tags = row.get("tags") or []
    body = repair_text(strip_html(row.get("description", "")))
    blob = " ".join([body] + [str(t) for t in tags])

    sponsorship = "unknown"
    if row.get("visa_sponsorship") is True:
        sponsorship = "confirmed"
    elif row.get("visa_sponsorship") is False:
        sponsorship = "denied"
    else:
        sponsorship = detect_sponsorship(blob)

    posted = row.get("created_at")
    if isinstance(posted, int):
        posted = datetime.fromtimestamp(posted, timezone.utc).isoformat(timespec="seconds")

    return {
        "dedup_key": stable_key(
            "arbeitnow", raw.get("external_id"), raw.get("url"), title, company, city
        ),
        "title": title,
        "company_name": company,
        "country": country,
        "city": city,
        "remote": "remote" if row.get("remote") or "remote" in fold(location) else "onsite",
        "employment_type": ",".join(row.get("job_types") or []),
        "posted_at": posted,
        "url": raw.get("url"),
        "description": body,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "sponsorship_status": sponsorship,
        "language_required": detect_language(blob),
        "via_agency": detect_agency(company),
        "source_ids": [source_id],
    }


def from_remotive(raw, source_id):
    row = raw["payload"]
    tags = " ".join(str(t) for t in (row.get("tags") or []))
    return build_job(
        "remotive", raw, source_id,
        title=row.get("title"),
        company=row.get("company_name"),
        location=row.get("candidate_required_location"),
        body=row.get("description"),
        posted=row.get("publication_date"),
        url=row.get("url"),
        employment_type=row.get("job_type"),
        remote="remote",
        extra=tags + " " + str(row.get("category") or ""),
    )


def from_remoteok(raw, source_id):
    row = raw["payload"]
    tags = " ".join(str(t) for t in (row.get("tags") or []))
    return build_job(
        "remoteok", raw, source_id,
        title=row.get("position") or row.get("title"),
        company=row.get("company"),
        location=row.get("location"),
        body=row.get("description"),
        posted=row.get("date") or row.get("epoch"),
        url=row.get("url") or row.get("apply_url"),
        remote="remote",
        salary_min=row.get("salary_min") or None,
        salary_max=row.get("salary_max") or None,
        salary_currency="USD",
        extra=tags,
    )


def split_wwr_title(text):
    line = clean_line(text)
    if ":" in line:
        company, _, title = line.partition(":")
        return company.strip(), title.strip()
    return "", line


def from_wwr(raw, source_id):
    row = raw["payload"]
    company, title = split_wwr_title(row.get("title"))
    return build_job(
        "wwr", raw, source_id,
        title=title,
        company=company,
        location=row.get("region"),
        body=row.get("description"),
        posted=row.get("pubDate"),
        url=row.get("link"),
        employment_type=row.get("type"),
        remote="remote",
        extra=row.get("category"),
    )


def from_adzuna(raw, source_id):
    row = raw["payload"]
    area = row.get("location") or {}
    parts = [p for p in (area.get("area") or []) if p]
    location = ", ".join(reversed(parts)) if parts else area.get("display_name")
    predicted = str(row.get("salary_is_predicted") or "0") == "1"
    country = str(row.get("_country") or raw.get("country") or "").lower()
    contract = " ".join(
        str(row.get(key) or "") for key in ("contract_time", "contract_type")
    ).strip()
    return build_job(
        "adzuna", raw, source_id,
        title=row.get("title"),
        company=(row.get("company") or {}).get("display_name"),
        location=location,
        body=row.get("description"),
        posted=row.get("created"),
        url=row.get("redirect_url"),
        employment_type=contract or None,
        salary_min=None if predicted else row.get("salary_min"),
        salary_max=None if predicted else row.get("salary_max"),
        salary_currency=ADZUNA_CURRENCY.get(country, "EUR"),
        extra=(row.get("category") or {}).get("label"),
    )


def from_greenhouse(raw, source_id):
    row = raw["payload"]
    location = (row.get("location") or {}).get("name")
    if not location:
        offices = row.get("offices") or []
        location = offices[0].get("location") if offices else None
    return build_job(
        "greenhouse", raw, source_id,
        title=row.get("title"),
        company=row.get("_company") or row.get("company_name"),
        location=location,
        body=row.get("content"),
        posted=row.get("first_published") or row.get("updated_at"),
        url=row.get("absolute_url"),
        extra=" ".join(
            str(m.get("value") or "") for m in (row.get("metadata") or [])
            if isinstance(m, dict)
        ),
    )


def from_lever(raw, source_id):
    row = raw["payload"]
    categories = row.get("categories") or {}
    salary = row.get("salaryRange") or {}
    interval = str(salary.get("interval") or "")
    yearly = "year" in interval or not interval
    workplace = str(row.get("workplaceType") or "").lower()
    body = " ".join(
        str(row.get(key) or "") for key in ("descriptionPlain", "additionalPlain")
    )
    return build_job(
        "lever", raw, source_id,
        title=row.get("text"),
        company=row.get("_company"),
        location=categories.get("location"),
        body=body,
        posted=row.get("createdAt"),
        url=row.get("hostedUrl") or row.get("applyUrl"),
        employment_type=categories.get("commitment"),
        remote="remote" if workplace == "remote" else None,
        salary_min=salary.get("min") if yearly else None,
        salary_max=salary.get("max") if yearly else None,
        salary_currency=salary.get("currency"),
        extra=" ".join(str(categories.get(k) or "") for k in ("department", "team")),
    )


def from_ashby(raw, source_id):
    row = raw["payload"]
    extras = [x for x in (row.get("secondaryLocations") or []) if isinstance(x, str)]
    location = row.get("location") or (extras[0] if extras else None)
    return build_job(
        "ashby", raw, source_id,
        title=row.get("title"),
        company=row.get("_company"),
        location=location,
        body=row.get("descriptionPlain") or row.get("descriptionHtml"),
        posted=row.get("publishedAt"),
        url=row.get("jobUrl") or row.get("applyUrl"),
        employment_type=row.get("employmentType"),
        remote="remote" if row.get("isRemote") else None,
        extra=" ".join([str(row.get("department") or ""), str(row.get("team") or "")]),
    )


def from_workable(raw, source_id):
    row = raw["payload"]
    places = row.get("locations") or []
    first = places[0] if places and isinstance(places[0], dict) else {}
    location = ", ".join(
        str(p) for p in [
            row.get("city") or first.get("city"),
            row.get("country") or first.get("country"),
        ] if p
    )
    body = " ".join(
        str(row.get(key) or "") for key in ("description", "requirements", "benefits")
    )
    return build_job(
        "workable", raw, source_id,
        title=row.get("title") or row.get("full_title"),
        company=row.get("_company"),
        location=location,
        body=body,
        posted=row.get("published_on") or row.get("created_at"),
        url=row.get("url") or row.get("shortlink"),
        employment_type=row.get("employment_type"),
        remote="remote" if row.get("telecommuting") else None,
        extra=" ".join([str(row.get("department") or ""), str(row.get("function") or "")]),
    )


NORMALIZERS = {
    "arbeitnow": from_arbeitnow,
    "remotive": from_remotive,
    "remoteok": from_remoteok,
    "wwr": from_wwr,
    "adzuna": from_adzuna,
    "greenhouse": from_greenhouse,
    "lever": from_lever,
    "ashby": from_ashby,
    "workable": from_workable,
}


def normalize(source_name, raw, source_id):
    fn = NORMALIZERS.get(source_name)
    if not fn:
        raise ValueError("no normalizer for " + source_name)
    return fn(raw, source_id)
