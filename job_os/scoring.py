"""Explainable, candidate-specific job scoring and safety checks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
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
    "data": "data_reporting_bi", "report": "data_reporting_bi", "business intelligence": "data_reporting_bi", "bi ": "data_reporting_bi",
    "fintech": "fintech", "finance": "fintech", "bank": "fintech",
    "ai": "applied_ai_automation", "automation": "applied_ai_automation", "machine learning": "applied_ai_automation",
    "front": "web_frontend", "web": "web_frontend", "react": "web_frontend",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _component(value: float, weight: int) -> int:
    return round(max(0.0, min(1.0, value)) * weight)


def _graduation_year(profile: Dict[str, Any]) -> int:
    match = re.search(r"20\d{2}", profile.get("graduation", ""))
    return int(match.group()) if match else 2029


def safety_flags(job: Dict[str, Any], profile: Dict[str, Any] | None = None) -> list[Dict[str, str]]:
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

    years = [int(y) for y in re.findall(r"graduat(?:e|ion)[^\d]{0,30}(20\d{2})", text)]
    if years and max(years) < _graduation_year(profile):
        flags.append({"severity": "high", "code": "graduation_mismatch", "message": f"Posting appears to require graduation by {max(years)}, before configured May {_graduation_year(profile)}."})

    salary_min = job.get("salary_min")
    salary_unit = job.get("salary_unit")
    if salary_min is not None and salary_unit in ("hour", "hr") and float(salary_min) < 17.60:
        flags.append({"severity": "high", "code": "below_minimum_wage", "message": "Listed hourly pay appears below the configured Ontario minimum-wage safety floor; verify the current legal rate."})
    if any(x in text for x in ("senior ", "staff engineer", "principal ", "5+ years", "five years")):
        flags.append({"severity": "medium", "code": "seniority", "message": "Seniority or experience requirements are above the target level."})
    return flags


def choose_resume_profile(job: Dict[str, Any]) -> str:
    text = _norm(f"{job.get('title', '')} {job.get('description', '')}")
    for keyword, profile_name in PROFILE_BY_ROLE.items():
        if keyword in text:
            return profile_name
    return "general_software"


def choose_project(job: Dict[str, Any]) -> str:
    text = _norm(f"{job.get('title', '')} {job.get('description', '')} {job.get('industry', '')}")
    if any(x in text for x in ("accessibility", "hardware", "embedded", "gemini", "computer vision")):
        return "S.E.N.S.E."
    if any(x in text for x in ("finance", "fintech", "trading", "data", "risk", "python", "analytics")):
        return "MalpariBot"
    return "JobApplier"


def score_job(job: Dict[str, Any], profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
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

    internship = any(x in full_text for x in ("intern", "co op", "coop", "student"))
    entry = any(x in full_text for x in ("entry level", "junior", "new grad"))
    senior = any(x in full_text for x in ("senior", "staff", "principal", "5+ years"))
    suitability = 1.0 if internship else 0.65 if entry else 0.1 if senior else 0.4

    location = _norm(job.get("location", ""))
    work_mode = job.get("work_mode", "unknown")
    local = any(_norm(place) in location for place in profile.get("target_locations", []))
    canada = "canada" in location or any(city in location for city in ("toronto", "ontario", "vaughan", "markham", "brampton", "mississauga", "north york"))
    location_fit = 1.0 if local or (work_mode == "remote" and canada) else 0.78 if canada else 0.55 if not location or location == "unspecified" else 0.35

    start = _norm(job.get("start_date") or "")
    start_fit = 1.0 if any(x in start for x in ("summer 2026", "fall 2026", "2027", "2028", "2029")) else 0.7 if not start else 0.45
    target_role_terms = ["software", "developer", "web", "qa", "test", "data", "report", "bi", "fintech", "finance technology", "ai", "automation", "technical analyst"]
    role_fit = min(1.0, sum(1 for term in target_role_terms if term in title_text) / 2)
    industry_fit = 1.0 if any(x in full_text for x in ("fintech", "finance", "software", "technology", "data", "accessibility")) else 0.6
    resume_profile = choose_resume_profile(job)
    project = choose_project(job)
    resume_strength = 0.95 if matched and (internship or entry) else 0.75 if matched else 0.55
    risk_fit = 1.0 - min(0.85, len(missing) / max(1, len(required)))
    effort_map = {"low": 1.0, "medium": 0.7, "high": 0.4}
    effort = effort_map.get(job.get("application_effort", "medium"), 0.7)
    likelihood = (technical_ratio + suitability + role_fit + resume_strength) / 4

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
    flags = safety_flags(job, profile)
    if any(flag["severity"] == "block" for flag in flags):
        score = min(score, 15)
    elif any(flag["severity"] == "high" for flag in flags):
        score = min(score, 54)

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
        "strategy": "Tailor the selected profile, verify every claim, then apply early through the employer's official portal." if score >= 52 else "Deprioritize unless a referral or unusually strong motivation offsets the gaps.",
        "safety_flags": flags,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
