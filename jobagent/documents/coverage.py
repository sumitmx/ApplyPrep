import re

STOPWORDS = {
    "and", "the", "for", "with", "you", "our", "are", "will", "have", "has",
    "this", "that", "from", "your", "who", "was", "not", "all", "can", "but",
    "job", "role", "work", "team", "years", "experience", "working", "about",
    "what", "how", "why", "when", "into", "them", "they", "their", "its",
    "wir", "und", "der", "die", "das", "ein", "eine", "mit", "fur", "von",
}

_WORD = re.compile(r"[a-z][a-z0-9+#./-]{2,}")


def terms(text):
    found = []
    for word in _WORD.findall((text or "").lower()):
        cleaned = word.strip("./-")
        if len(cleaned) > 2 and cleaned not in STOPWORDS:
            found.append(cleaned)
    return found


TECH_TERMS = {
    "python", "java", "javascript", "typescript", "golang", "rust", "kotlin",
    "scala", "ruby", "php", "swift", "csharp", "c++", "bash", "powershell",
    "sql", "nosql", "graphql", "html", "css",
    "react", "angular", "vue", "svelte", "next.js", "node", "django", "flask",
    "fastapi", "spring", "rails", "laravel", "symfony", "dotnet",
    "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "ansible",
    "jenkins", "gitlab", "github", "argocd", "helm", "openshift", "serverless",
    "lambda", "ec2", "s3", "bigquery", "redshift", "snowflake", "databricks",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "cassandra", "dynamodb", "mssql", "oracle", "kafka", "rabbitmq", "pubsub",
    "airflow", "dbt", "spark", "hadoop", "flink", "glue", "dataflow",
    "pytorch", "tensorflow", "sklearn", "pandas", "numpy", "langchain",
    "vertex", "sagemaker", "mlflow", "kubeflow", "huggingface",
    "llm", "rag", "nlp", "mlops", "devops", "sre", "cicd", "ci/cd",
    "microservices", "rest", "grpc", "soap", "api", "oauth", "saml",
    "uipath", "blueprism", "automationanywhere", "rpa", "sap", "salesforce",
    "servicenow", "workday", "dynamics", "sharepoint", "shopware", "magento",
    "prometheus", "grafana", "datadog", "splunk", "opentelemetry", "sentry",
    "linux", "windows", "git", "jira", "confluence", "agile", "scrum", "safe",
    "terraformer", "packer", "vault", "consul", "istio", "nginx", "kafka",
    "looker", "tableau", "powerbi", "qlik", "superset",
}


def phrases(text):
    words = terms(text)
    out = set(words)
    for i in range(len(words) - 1):
        out.add(words[i] + " " + words[i + 1])
        if i + 2 < len(words):
            out.add(words[i] + " " + words[i + 1] + " " + words[i + 2])
    return out


ALIASES = {
    "gcp": ["google cloud platform", "google cloud"],
    "google cloud platform": ["gcp"],
    "k8s": ["kubernetes"],
    "kubernetes": ["k8s"],
    "postgres": ["postgresql"],
    "postgresql": ["postgres"],
    "ci/cd": ["cicd", "continuous integration"],
    "cicd": ["ci/cd"],
    "vertex": ["vertex ai"],
    "vertex ai": ["vertex"],
    "sklearn": ["scikit-learn"],
    "dotnet": [".net"],
}


def skill_names(master):
    owned = {}
    for tier in ("core", "working", "familiar"):
        for entry in (master or {}).get("skills", {}).get(tier) or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name:
                owned[str(name).lower()] = tier

    for role in (master or {}).get("experience") or []:
        for bullet in role.get("bullets") or []:
            for tag in (bullet.get("skills") or []):
                owned.setdefault(str(tag).lower(), "experience")
    for project in (master or {}).get("projects") or []:
        for tag in (project.get("skills") or []):
            owned.setdefault(str(tag).lower(), "experience")

    for name in list(owned):
        for alias in ALIASES.get(name, []):
            owned.setdefault(alias, owned[name])
    return owned


def analyse(job_description, cv_text, master):
    wanted = phrases(job_description)
    in_cv = phrases(cv_text)
    owned = skill_names(master)

    covered = []
    fixable = []
    real_gap = []

    for skill, tier in owned.items():
        if skill in wanted:
            if skill in in_cv:
                covered.append({"term": skill, "tier": tier})
            else:
                fixable.append({"term": skill, "tier": tier})

    owned_words = set()
    for skill in owned:
        owned_words.update(skill.split())

    for term in sorted(wanted & TECH_TERMS):
        if term in owned or term in owned_words or term in in_cv:
            continue
        real_gap.append({"term": term})

    return {
        "covered": sorted(covered, key=lambda x: x["term"]),
        "fixable": sorted(fixable, key=lambda x: x["term"]),
        "real_gap": real_gap,
        "counts": {
            "covered": len(covered),
            "fixable": len(fixable),
            "real_gap": len(real_gap),
        },
    }
