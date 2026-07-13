"""Deterministic parser for pasted job descriptions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable


SKILL_ALIASES = {
    "Java": ["java"], "Python": ["python"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"], "HTML": ["html"], "CSS": ["css"],
    "SQL": ["sql"], "MySQL": ["mysql"], "React": ["react"],
    "React Native": ["react native"], "Next.js": ["next.js", "nextjs"],
    "Express.js": ["express.js", "expressjs", "express"], "Flask": ["flask"],
    "Pandas": ["pandas"], "Tailwind CSS": ["tailwind"], "Git": ["git"],
    "Docker": ["docker"], "Figma": ["figma"], "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"], "Power BI": ["power bi", "powerbi"], "Tableau": ["tableau"],
    "C++": ["c++"], "C#": ["c#", "c sharp"], ".NET": [".net", "dotnet"],
    "Node.js": ["node.js", "nodejs"], "Selenium": ["selenium"],
    "Playwright": ["playwright"], "Jest": ["jest"], "Pytest": ["pytest"],
    "Raspberry Pi": ["raspberry pi"], "Arduino": ["arduino"],
}


def _contains_alias(text: str, alias: str) -> bool:
    if len(alias) <= 2 and alias.isalnum():
        return bool(re.search(rf"\b{re.escape(alias)}\b", text))
    return alias in text


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    return sorted({name for name, aliases in SKILL_ALIASES.items() if any(_contains_alias(lowered, alias) for alias in aliases)})


def _sentences(text: str) -> Iterable[str]:
    return (part.strip() for part in re.split(r"[\n\r]+|(?<=[.!?])\s+", text) if part.strip())


def _extract_salary(text: str) -> tuple[float | None, float | None, str | None]:
    match = re.search(
        r"\$\s*([0-9]{2,3}(?:,[0-9]{3})?(?:\.\d+)?)\s*(?:-|to|–)\s*\$?\s*([0-9]{2,3}(?:,[0-9]{3})?(?:\.\d+)?)\s*(?:/|per\s+)?(hour|hr|year|annum)?",
        text, re.I,
    )
    if not match:
        return None, None, None
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", ""))
    unit = (match.group(3) or "").lower()
    if not unit and low > 1000:
        unit = "year"
    return low, high, unit or None


def _extract_date(text: str, label: str) -> str | None:
    match = re.search(
        rf"{label}[^\n.]{{0,30}}((?:january|february|march|april|may|june|july|august|september|october|november|december|summer|fall|winter|spring)\s+20\d{{2}})",
        text, re.I,
    )
    return match.group(1).title() if match else None


def parse_job_description(text: str, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Parse safe, useful fields without pretending uncertain data is known."""
    overrides = overrides or {}
    lowered = text.lower()
    sentences = list(_sentences(text))
    required_text = " ".join(s for s in sentences if any(k in s.lower() for k in ("required", "must", "qualification", "minimum")))
    preferred_text = " ".join(s for s in sentences if any(k in s.lower() for k in ("preferred", "nice to have", "asset", "bonus")))
    all_skills = extract_skills(text)
    required_skills = extract_skills(required_text)
    preferred_skills = [skill for skill in extract_skills(preferred_text) if skill not in required_skills]
    if not required_skills:
        required_skills = all_skills

    salary_min, salary_max, salary_unit = _extract_salary(text)
    def number_override(name, fallback):
        value = overrides.get(name)
        if value in (None, ""):
            return fallback
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
    work_mode = "remote" if "remote" in lowered else "hybrid" if "hybrid" in lowered else "on_site" if any(x in lowered for x in ("on-site", "onsite", "in office")) else "unknown"
    coop = any(term in lowered for term in ("co-op", "coop", "internship", "student position"))
    seniority = "internship_coop" if any(term in lowered for term in ("intern", "co-op", "coop", "student")) else "new_grad" if any(term in lowered for term in ("new grad", "entry level", "junior")) else "senior" if any(term in lowered for term in ("senior", "staff", "principal", "lead developer")) else "unspecified"
    sponsorship = "not_available" if any(term in lowered for term in ("no sponsorship", "cannot sponsor", "not sponsor")) else "required" if "sponsorship required" in lowered else "unknown"

    term_match = re.search(r"\b(4|8|12|16)\s*[- ]?(?:month|months)\b", lowered)
    industry = "fintech" if any(x in lowered for x in ("fintech", "banking", "capital markets", "financial services")) else "technology" if any(x in lowered for x in ("software", "technology", "saas")) else "other"
    result = {
        "description": text.strip(),
        "title": overrides.get("title") or "Untitled opportunity",
        "company": overrides.get("company") or "Unknown company",
        "location": overrides.get("location") or ("Remote Canada" if "remote" in lowered and "canada" in lowered else "Unspecified"),
        "job_url": overrides.get("job_url") or overrides.get("application_url") or "",
        "source": overrides.get("source") or "manual",
        "work_mode": overrides.get("work_mode") or work_mode,
        "term_length": overrides.get("term_length") or (f"{term_match.group(1)} months" if term_match else None),
        "start_date": overrides.get("start_date") or _extract_date(text, "start(?:ing)?"),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "tech_stack": all_skills,
        "work_authorization": overrides.get("work_authorization") or None,
        "sponsorship": overrides.get("sponsorship") or sponsorship,
        "coop_eligible": bool(overrides.get("coop_eligible", coop)),
        "industry": overrides.get("industry") or industry,
        "seniority_level": overrides.get("seniority_level") or seniority,
        "posting_date": overrides.get("posting_date"),
        "deadline": overrides.get("deadline") or _extract_date(text, "deadline|apply by"),
        "salary_min": number_override("salary_min", salary_min),
        "salary_max": number_override("salary_max", salary_max),
        "salary_unit": overrides.get("salary_unit", salary_unit),
        "application_effort": overrides.get("application_effort") or ("high" if any(x in lowered for x in ("transcript", "cover letter", "portfolio", "assessment")) else "medium"),
        "required_documents": [name for name, terms in {
            "resume": ("resume", "cv"), "cover_letter": ("cover letter",),
            "transcript": ("transcript",), "portfolio": ("portfolio",),
        }.items() if any(term in lowered for term in terms)],
        "login_portal": overrides.get("login_portal") or None,
        "notes": overrides.get("notes") or "",
    }
    return result


def parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
