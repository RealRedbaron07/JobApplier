"""Explainable, candidate-specific job scoring and safety checks."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict

from .profile import load_profile


WEIGHTS = {
    "technical_skill_match": 24,
    "internship_coop_suitability": 15,
    "location_commute_fit": 12,
    "start_date_fit": 10,
    "role_type_fit": 12,
    "industry_fit": 7,
    "resume_strength_fit": 8,
    "missing_requirements_risk": 6,
    "application_effort": 3,
    "likelihood_worth_applying": 3,
}

PROFILE_BY_ROLE = {
    "qa": "qa_testing", "test": "qa_testing", "quality": "qa_testing",
    "data": "data_reporting_bi", "report": "data_reporting_bi", "business intelligence": "data_reporting_bi", "bi": "data_reporting_bi",
    "fintech": "fintech", "finance": "fintech", "bank": "fintech",
    "ai": "applied_ai_automation", "automation": "applied_ai_automation", "machine learning": "applied_ai_automation",
    "front end": "web_frontend", "frontend": "web_frontend", "web": "web_frontend", "react": "web_frontend",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _component(value: float, weight: int) -> int:
    return round(max(0.0, min(1.0, value)) * weight)


def _has_phrase(text: str, phrase: str) -> bool:
    pattern = re.escape(_norm(phrase)).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


def _graduation_year(profile: Dict[str, Any]) -> int:
    match = re.search(r"20\d{2}", profile.get("graduation", ""))
    return int(match.group()) if match else 2029


def ontario_minimum_wage(as_of: date | datetime | None = None) -> float:
    """Return the published Ontario general minimum-wage floor for supported dates."""
    current = as_of or datetime.now(timezone.utc)
    if isinstance(current, datetime):
        current = current.date()
    return 17.95 if current >= date(2026, 10, 1) else 17.60


def _wage_reference_date(job: Dict[str, Any], fallback: date | datetime | None = None) -> date | datetime | None:
    start = _norm(str(job.get("start_date") or ""))
    year_match = re.search(r"20\d{2}", start)
    if not year_match:
        return fallback
    year = int(year_match.group())
    if "fall" in start:
        return date(year, 10, 1)
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "winter": 1, "spring": 5, "summer": 6,
    }
    month = next((number for name, number in month_map.items() if name in start), 1)
    return date(year, month, 1)


def safety_flags(job: Dict[str, Any], profile: Dict[str, Any] | None = None, as_of: date | datetime | None = None) -> list[Dict[str, str]]:
    profile = profile or load_profile()
    text = _norm(" ".join(str(job.get(key, "")) for key in ("title", "description", "notes", "work_authorization")))
    flags: list[Dict[str, str]] = []
    if any(x in text for x in ("pay a fee", "training fee", "application fee", "purchase equipment", "send money", "crypto payment")):
        flags.append({"severity": "block", "code": "payment_request", "message": "Posting asks the applicant for money or a fee."})
    if any(x in text for x in ("unpaid internship", "unpaid position", "volunteer internship")):
        flags.append({"severity": "high", "code": "unpaid", "message": "Role appears unpaid; verify Ontario employment standards and school rules."})
    if any(x in text for x in ("must misrepresent", "lie about", "fabricate experience")):
        flags.append({"severity": "block", "code": "dishonesty", "message": "Application appears to require a false claim."})
    if job.get("sponsorship") == "required" or ("must require sponsorship" in text):
        flags.append({"severity": "high", "code": "sponsorship", "message": "Role may require sponsorship outside the candidate's Canadian authorization."})

    us_authorization = any(phrase in text for phrase in (
        "authorized to work in the us", "authorized to work in the united states",
        "us work authorization", "u s work authorization", "work authorization in the united states",
        "eligible to work in the us", "eligible to work in the united states",
    ))
    other_country_authorization = any(phrase in text for phrase in (
        "uk work authorization", "eu work authorization", "authorized to work in the uk",
        "authorized to work in the european union",
    ))
    if us_authorization or other_country_authorization:
        flags.append({"severity": "high", "code": "outside_canada_authorization", "message": "Posting appears to require work authorization outside Canada; Canadian permanent residence does not establish that eligibility."})

    years = [int(y) for y in re.findall(r"graduat(?:e|ing|ion)[^\d]{0,40}(20\d{2})", text)]
    if years and max(years) < _graduation_year(profile):
        flags.append({"severity": "high", "code": "graduation_mismatch", "message": f"Posting appears to require graduation by {max(years)}, before the configured {profile.get('graduation') or _graduation_year(profile)} date."})

    salary_min = job.get("salary_min")
    salary_unit = job.get("salary_unit")
    wage_floor = ontario_minimum_wage(_wage_reference_date(job, as_of))
    if salary_min is not None and str(salary_unit or "").lower() in ("hour", "hr") and float(salary_min) < wage_floor:
        flags.append({"severity": "high", "code": "below_minimum_wage", "message": f"Listed hourly pay appears below Ontario's ${wage_floor:.2f} general minimum-wage floor for the applicable date; verify role coverage and the current legal rate."})
    if any(x in text for x in ("senior ", "staff engineer", "principal ", "5+ years", "five years")):
        flags.append({"severity": "medium", "code": "seniority", "message": "Seniority or experience requirements are above the target level."})
    return flags


def choose_resume_profile(job: Dict[str, Any]) -> str:
    text = _norm(f"{job.get('title', '')} {job.get('description', '')}")
    for keyword, profile_name in PROFILE_BY_ROLE.items():
        if _has_phrase(text, keyword):
            return profile_name
    return "general_software"


def choose_project(job: Dict[str, Any]) -> str:
    text = _norm(f"{job.get('title', '')} {job.get('description', '')} {job.get('industry', '')}")
    if any(x in text for x in ("accessibility", "hardware", "embedded", "gemini", "computer vision")):
        return "S.E.N.S.E."
    if any(x in text for x in ("finance", "fintech", "trading", "data", "risk", "python", "analytics")):
        return "MalpariBot"
    return "JobApplier"


def _start_date_fit(value: Any) -> float:
    start = _norm(str(value or ""))
    if not start:
        return 0.7
    year_match = re.search(r"20\d{2}", start)
    if not year_match:
        return 0.55
    year = int(year_match.group())
    if year > 2026:
        return 1.0
    if year < 2026:
        return 0.1
    if any(term in start for term in ("summer", "fall", "june", "july", "august", "september", "october", "november", "december")):
        return 1.0
    return 0.35


def _posting_recency(value: Any, as_of: date | datetime | None = None) -> float:
    if not value:
        return 0.65
    try:
        posted = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        posted_date = posted.date()
    except (TypeError, ValueError):
        return 0.65
    current = as_of or datetime.now(timezone.utc)
    current_date = current.date() if isinstance(current, datetime) else current
    age = max(0, (current_date - posted_date).days)
    return 1.0 if age <= 7 else 0.82 if age <= 21 else 0.6 if age <= 45 else 0.35


def score_job(job: Dict[str, Any], profile: Dict[str, Any] | None = None, as_of: date | datetime | None = None) -> Dict[str, Any]:
    profile = profile or load_profile()
    title_text = _norm(job.get("title", ""))
    full_text = _norm(f"{job.get('title', '')} {job.get('description', '')} {job.get('industry', '')}")
    candidate_skills = {_norm(skill) for skill in profile.get("skills", [])}
    required = job.get("required_skills") or []
    preferred = job.get("preferred_skills") or []
    matched = [skill for skill in required if _norm(skill) in candidate_skills]
    missing = [skill for skill in required if _norm(skill) not in candidate_skills]
    preferred_matched = [skill for skill in preferred if _norm(skill) in candidate_skills]
    technical_ratio = (len(matched) + 0.4 * len(preferred_matched)) / max(1, len(required) + 0.4 * len(preferred)) if required or preferred else 0.55

    internship = bool(job.get("coop_eligible")) or any(x in full_text for x in ("intern", "co op", "coop", "student"))
    entry = any(x in full_text for x in ("entry level", "junior", "new grad"))
    senior = any(x in full_text for x in ("senior", "staff", "principal", "5+ years"))
    suitability = 1.0 if internship else 0.65 if entry else 0.1 if senior else 0.4

    location = _norm(job.get("location", ""))
    work_mode = job.get("work_mode", "unknown")
    local = any(_norm(place) in location for place in profile.get("target_locations", []))
    canada = "canada" in location or any(city in location for city in ("toronto", "ontario", "vaughan", "markham", "brampton", "mississauga", "north york"))
    location_fit = 1.0 if local or (work_mode == "remote" and canada) else 0.78 if canada else 0.55 if not location or location == "unspecified" else 0.35

    start_fit = _start_date_fit(job.get("start_date"))
    target_role_terms = ["software", "developer", "web", "qa", "test", "data", "report", "bi", "fintech", "finance technology", "ai", "automation", "technical analyst"]
    role_fit = min(1.0, sum(1 for term in target_role_terms if _has_phrase(title_text, term)) / 2)
    industry_fit = 1.0 if any(x in full_text for x in ("fintech", "finance", "software", "technology", "data", "accessibility")) else 0.6
    resume_profile = choose_resume_profile(job)
    project = choose_project(job)
    resume_strength = 0.95 if matched and (internship or entry) else 0.75 if matched else 0.55
    risk_fit = 1.0 - min(0.85, len(missing) / max(1, len(required)))
    effort_map = {"low": 1.0, "medium": 0.7, "high": 0.4}
    effort = effort_map.get(job.get("application_effort", "medium"), 0.7)
    recency = _posting_recency(job.get("posting_date") or job.get("posted_date"), as_of)
    likelihood = (technical_ratio + suitability + role_fit + resume_strength + recency) / 5

    raw = {
        "technical_skill_match": technical_ratio,
        "internship_coop_suitability": suitability,
        "location_commute_fit": location_fit,
        "start_date_fit": start_fit,
        "role_type_fit": role_fit,
        "industry_fit": industry_fit,
        "resume_strength_fit": resume_strength,
        "missing_requirements_risk": risk_fit,
        "application_effort": effort,
        "likelihood_worth_applying": likelihood,
    }
    breakdown = {key: {"points": _component(value, WEIGHTS[key]), "max": WEIGHTS[key]} for key, value in raw.items()}
    score = sum(item["points"] for item in breakdown.values())
    flags = safety_flags(job, profile, as_of)
    flags.extend({
        "severity": "medium",
        "code": "missing_technology",
        "message": f"Required technology is not in the configured candidate profile: {skill}.",
    } for skill in missing)
    if any(flag["severity"] == "block" for flag in flags):
        score = min(score, 15)
    elif any(flag["severity"] == "high" for flag in flags):
        score = min(score, 54)

    has_block = any(flag["severity"] == "block" for flag in flags)
    has_high = any(flag["severity"] == "high" for flag in flags)
    category = "strong_apply" if score >= 82 else "apply" if score >= 68 else "maybe" if score >= 52 else "low_priority" if score >= 35 else "skip"
    why = []
    if matched:
        why.append(f"Matches {len(matched)} required skills: {', '.join(matched[:6])}.")
    if internship:
        why.append("The posting is explicitly internship/co-op aligned.")
    if location_fit >= 0.78:
        why.append("The location/work-mode fits the configured Canada search area.")
    risks = [f"Missing or unverified required skill: {skill}." for skill in missing]
    risks.extend(flag["message"] for flag in flags)
    return {
        "overall_score": int(score),
        "category": category,
        "breakdown": breakdown,
        "matched_skills": matched,
        "missing_skills": missing,
        "why_it_fits": why or ["The posting has partial alignment but needs manual review."],
        "risks": risks or ["No major deterministic risks detected; verify the complete posting manually."],
        "resume_profile": resume_profile,
        "project_to_emphasize": project,
        "strategy": (
            "Do not apply unless the blocking eligibility or integrity issue is resolved with verified information."
            if has_block else
            "Pause and verify the high-risk eligibility or pay issue before spending time on this application."
            if has_high else
            "Tailor the selected profile, verify every claim, then apply early through the employer's official portal."
            if score >= 52 else
            "Deprioritize unless a referral or unusually strong motivation offsets the gaps."
        ),
        "safety_flags": flags,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
