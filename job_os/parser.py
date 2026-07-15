"""Deterministic parser for pasted job descriptions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable


SKILL_ALIASES = {
    "Java": ["java"], "Python": ["python"], "JavaScript": ["javascript"],
    "TypeScript": ["typescript"], "HTML": ["html"], "CSS": ["css"],
    "SQL": ["sql"], "MySQL": ["mysql"], "React": ["react"],
    "React Native": ["react native"], "Next.js": ["next.js", "nextjs"],
    "Express.js": ["express.js", "expressjs", "express"], "Flask": ["flask"],
    "Pandas": ["pandas"], "Tailwind CSS": ["tailwind"], "Git": ["git"],
    "Docker": ["docker"], "Figma": ["figma"], "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"], "Power BI": ["power bi", "powerbi"], "Tableau": ["tableau"],
    "C++": ["c++"], "C#": ["c#", "c sharp"], ".NET": [".net", "dotnet"],
    "Node.js": ["node.js", "nodejs"], "Selenium": ["selenium"],
    "Playwright": ["playwright"], "Jest": ["jest"], "Pytest": ["pytest"],
    "Go": ["golang", "go language"], "Rust": ["rust"], "Ruby": ["ruby"],
    "Swift": ["swift"], "Terraform": ["terraform"], "Kubernetes": ["kubernetes", "k8s"],
    "Manual QA": ["manual qa", "manual testing"], "Regression Testing": ["regression testing"],
    "Bug Reporting": ["bug reporting", "bug reports"], "CI/CD Checks": ["ci/cd", "continuous integration"],
    "Gemini API": ["gemini api"], "ElevenLabs API": ["elevenlabs api"],
    "Yahoo Finance API": ["yahoo finance api"], "Gmail API": ["gmail api"],
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
        single = re.search(
            r"\$\s*([0-9]{2,3}(?:,[0-9]{3})?(?:\.\d+)?)\s*(?:/|per\s+)?(hour|hr|year|annum)",
            text, re.I,
        )
        if not single:
            return None, None, None
        value = float(single.group(1).replace(",", ""))
        return value, value, single.group(2).lower()
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", ""))
    unit = (match.group(3) or "").lower()
    if not unit and low > 1000:
        unit = "year"
    return low, high, unit or None


def _extract_date(text: str, label: str) -> str | None:
    match = re.search(
        rf"{label}[^\n.]{{0,35}}(20\d{{2}}-\d{{2}}-\d{{2}}|(?:january|february|march|april|may|june|july|august|september|october|november|december|summer|fall|winter|spring)(?:\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?)?\s+20\d{{2}})",
        text, re.I,
    )
    return match.group(1).title() if match else None


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if value in (None, ""):
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "y", "1", "eligible"}:
        return True
    if normalized in {"false", "no", "n", "0", "not eligible"}:
        return False
    return fallback


def _requirement_sections(text: str) -> tuple[str, str]:
    """Collect multiline required/preferred blocks while preserving a sentence fallback."""
    required_lines: list[str] = []
    preferred_lines: list[str] = []
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip(" \t-*•")
        if not line:
            continue
        required_heading = re.search(r"(?:^|[.!?]\s+)(?:required|requirements?|minimum qualifications?|qualifications?)\s*:?\s*(.*)$", line, re.I)
        preferred_heading = re.search(r"(?:^|[.!?]\s+)(?:preferred|preferred qualifications?|nice to have|assets?|bonus)\s*:?\s*(.*)$", line, re.I)
        if required_heading:
            section = "required"
            line = required_heading.group(1)
        elif preferred_heading:
            section = "preferred"
            line = preferred_heading.group(1)
        if not line:
            continue
        if re.search(r"\b(?:preferred|nice to have|asset|bonus)\b", line, re.I):
            preferred_lines.append(line)
            continue
        if section == "required":
            required_lines.append(line)
        elif section == "preferred":
            preferred_lines.append(line)
    sentences = list(_sentences(text))
    required_lines.extend(s for s in sentences if any(k in s.lower() for k in ("required", "must have", "minimum qualification")))
    preferred_lines.extend(s for s in sentences if any(k in s.lower() for k in ("preferred", "nice to have", "asset", "bonus")))
    return " ".join(dict.fromkeys(required_lines)), " ".join(dict.fromkeys(preferred_lines))


def parse_job_description(text: str, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Parse safe, useful fields without pretending uncertain data is known."""
    text = text if isinstance(text, str) else ""
    overrides = overrides if isinstance(overrides, dict) else {}
    lowered = text.lower()
    required_text, preferred_text = _requirement_sections(text)
    all_skills = extract_skills(text)
    required_skills = extract_skills(required_text)
    preferred_skills = [skill for skill in extract_skills(preferred_text) if skill not in required_skills]
    if not required_skills:
        required_skills = all_skills
    if isinstance(overrides.get("required_skills"), list):
        required_skills = [str(skill).strip() for skill in overrides["required_skills"] if str(skill).strip()]
    if isinstance(overrides.get("preferred_skills"), list):
        preferred_skills = [str(skill).strip() for skill in overrides["preferred_skills"] if str(skill).strip() and str(skill).strip() not in required_skills]
    all_skills = list(dict.fromkeys(all_skills + required_skills + preferred_skills))

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
    coop = any(term in lowered for term in ("co-op", "coop", "co op"))
    seniority = "internship_coop" if any(term in lowered for term in ("intern", "co-op", "coop", "student")) else "new_grad" if any(term in lowered for term in ("new grad", "entry level", "junior")) else "senior" if any(term in lowered for term in ("senior", "staff", "principal", "lead developer")) else "unspecified"
    sponsorship = (
        "not_available" if any(term in lowered for term in ("no sponsorship", "cannot sponsor", "not sponsor", "without sponsorship"))
        else "required" if any(term in lowered for term in ("sponsorship required", "requires sponsorship", "must require sponsorship"))
        else "available" if any(term in lowered for term in ("sponsorship available", "visa sponsorship", "will sponsor"))
        else "unknown"
    )

    term_match = re.search(r"\b(4|8|12|16)\s*[- ]?(?:month|months)\b", lowered)
    standalone_start = re.search(r"\b(summer|fall|winter|spring)\s+20\d{2}\b", text, re.I)
    industry = "fintech" if any(x in lowered for x in ("fintech", "banking", "capital markets", "financial services")) else "technology" if any(x in lowered for x in ("software", "technology", "saas")) else "other"
    job_type = (
        "internship" if "intern" in lowered else "co-op" if any(x in lowered for x in ("co-op", "coop"))
        else "part-time" if any(x in lowered for x in ("part-time", "part time"))
        else "contract" if "contract" in lowered else "full-time" if any(x in lowered for x in ("full-time", "full time"))
        else "unspecified"
    )
    result = {
        "description": text.strip(),
        "title": overrides.get("title") or "Untitled opportunity",
        "company": overrides.get("company") or "Unknown company",
        "location": overrides.get("location") or ("Remote Canada" if "remote" in lowered and "canada" in lowered else "Unspecified"),
        "job_url": overrides.get("job_url") or overrides.get("application_url") or "",
        "source": overrides.get("source") or "manual",
        "job_type": overrides.get("job_type") or job_type,
        "work_mode": overrides.get("work_mode") or work_mode,
        "term_length": overrides.get("term_length") or (f"{term_match.group(1)} months" if term_match else None),
        "start_date": overrides.get("start_date") or _extract_date(text, "start(?:ing)?") or (standalone_start.group(0).title() if standalone_start else None),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "requirements": required_text or None,
        "tech_stack": all_skills,
        "work_authorization": overrides.get("work_authorization") or None,
        "sponsorship": overrides.get("sponsorship") or sponsorship,
        "coop_eligible": _as_bool(overrides.get("coop_eligible"), coop),
        "industry": overrides.get("industry") or industry,
        "seniority_level": overrides.get("seniority_level") or seniority,
        "posting_date": overrides.get("posting_date") or overrides.get("posted_date"),
        "deadline": overrides.get("deadline") or _extract_date(text, "deadline|apply by"),
        "salary_min": number_override("salary_min", salary_min),
        "salary_max": number_override("salary_max", salary_max),
        "salary": overrides.get("salary") or None,
        "salary_unit": overrides.get("salary_unit") or salary_unit,
        "salary_currency": overrides.get("salary_currency") or ("CAD" if any(x in lowered for x in ("cad", "canadian dollar")) else "USD" if any(x in lowered for x in ("usd", "us dollar")) else None),
        "application_effort": overrides.get("application_effort") or ("high" if any(x in lowered for x in ("transcript", "cover letter", "portfolio", "assessment")) else "medium"),
        "required_documents": overrides.get("required_documents") if isinstance(overrides.get("required_documents"), list) else [name for name, terms in {
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
    cleaned = str(value).strip()
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        pass
    normalized = re.sub(r"(\d)(st|nd|rd|th)", r"\1", cleaned, flags=re.I)
    for pattern in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    return None
