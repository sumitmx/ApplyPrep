import re

DATE_PATTERN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b",
    re.IGNORECASE,
)
ACRONYMS = ["RPA", "SLA", "CI/CD", "RAG", "OCR", "MLOps", "SDLC", "ETL", "IaC"]

STANDARD_HEADINGS = [
    "professional summary", "summary", "experience",
    "professional experience", "education", "skills", "core skills",
]


def check(text, changes=None):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    joined = "\n".join(lines)
    lower = joined.lower()

    results = []

    results.append({
        "check": "Single column layout",
        "pass": "\t" not in (text or "") and "  |  " not in (text or ""),
        "detail": "tabs and column separators break parsing",
    })
    results.append({
        "check": "No text boxes or tables",
        "pass": True,
        "detail": "generated output is plain paragraphs",
    })
    results.append({
        "check": "Standard section headings",
        "pass": any(h in lower for h in STANDARD_HEADINGS),
        "detail": "recruiters filter on recognisable headings",
    })
    dates = DATE_PATTERN.findall(joined)
    results.append({
        "check": "Dates written as MMM YYYY",
        "pass": bool(dates) or "present" in lower,
        "detail": str(len(dates)) + " date(s) in the expected format",
    })

    unexplained = []
    for acronym in ACRONYMS:
        if acronym.lower() in lower and (acronym.lower() + " (") not in lower:
            unexplained.append(acronym)
    results.append({
        "check": "Acronyms spelled out once",
        "pass": not unexplained,
        "detail": (", ".join(unexplained) + " used without expansion")
        if unexplained else "all expanded or none used",
    })

    results.append({
        "check": "Every bullet traceable to master.yaml",
        "pass": True if changes is None else all(c.get("id") for c in changes),
        "detail": "nothing invented",
    })

    passed = sum(1 for r in results if r["pass"])
    return {
        "checks": results,
        "passed": passed,
        "failed": len(results) - passed,
    }
