"""Truthful candidate profile storage and defaults."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict

from config import Config


DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "Mustafa Alp ARI",
    "location": "Toronto, ON, Canada",
    "phone": "236-970-7998",
    "email": "malpari@icloud.com",
    "linkedin": "https://linkedin.com/in/mustafa-alp-ari",
    "github": "https://github.com/RealRedbaron07",
    "portfolio": "https://malpari.tech",
    "work_authorization": "Canadian Permanent Resident; legally authorized to work in Canada; no sponsorship needed in Canada",
    "graduation": "May 2029",
    "education": [{
        "institution": "York University",
        "degree": "BSc Honours Computer Science",
        "minor": "Economics",
        "expected_graduation": "May 2029",
    }],
    "target_roles": [
        "Software Developer Intern", "Web Developer Intern", "QA / Software Testing Intern",
        "Data / Reporting / BI Co-op", "Fintech / Finance Technology Co-op",
        "Applied AI / Automation Intern", "Technical Analyst Intern",
    ],
    "target_locations": [
        "Toronto", "GTA", "North York", "Vaughan", "Markham", "Brampton",
        "Mississauga", "Remote Canada", "Hybrid Ontario",
    ],
    "relocation": "Open to relocation within Canada for a strong role",
    "availability": "Internship/co-op roles starting Summer/Fall 2026 or later",
    "skills": [
        "Java", "Python", "JavaScript", "TypeScript", "HTML", "CSS", "SQL", "MySQL",
        "React", "React Native", "Expo", "Next.js", "Express.js", "Flask", "Streamlit",
        "Pandas", "Tailwind CSS", "Git", "GitHub", "Pull Requests", "Vercel", "SonarCloud",
        "GitGuardian", "Docker", "VS Code", "IntelliJ", "Linux", "macOS", "Windows", "Figma",
        "Gemini API", "ElevenLabs API", "Binance API", "Yahoo Finance API", "Gmail API",
        "Raspberry Pi", "Arduino", "Frontend Development", "Software Testing", "Manual QA",
        "Regression Testing", "Bug Reporting", "API Integration", "Debugging", "CI/CD Checks",
        "Code Review", "Hardware-Software Integration", "Accessibility", "Version Control",
        "Data Processing", "Automation", "Risk Management",
    ],
    "experience": [
        {
            "company": "Level UP / Riipen - NBA Cap Tracker",
            "title": "Software Developer Intern / Web Developer",
            "location": "Remote",
            "dates": "May 2026 - July 2026",
            "facts": [
                "Worked on a Next.js and TypeScript web application.",
                "Improved frontend navigation, the header, and Trade Machine behavior.",
                "Used Git branches, pull requests, code review, Vercel, GitGuardian, and SonarCloud checks.",
                "Refactored Navbar code and corrected season logic from 2025/26 through 2027/28.",
                "Fixed apron validation using season-specific salary data.",
                "Performed local QA and documented environment blockers.",
            ],
        },
        {
            "company": "Allymon via Riipen",
            "title": "Jr. Software Developer",
            "location": "Remote",
            "dates": "May 2026 - June 2026",
            "facts": [
                "Set up and debugged a full-stack fintech platform using Next.js, Express.js, and MySQL.",
                "Validated database, authentication, and admin workflows.",
                "Tested users, loans, and investor qualification flows and documented expected versus actual results.",
            ],
        },
        {
            "company": "Macro Tec Systems Inc. via Riipen",
            "title": "Software Developer Intern",
            "location": "Remote",
            "dates": "March 2026 - May 2026",
            "facts": [
                "Improved UI, navigation, user flows, and authentication-related screens in a React Native finance app.",
                "Merged Git branches and resolved conflicts while preserving newer functionality.",
            ],
        },
        {
            "company": "CSHub, York University",
            "title": "VP Events & Executive",
            "dates": "August 2025 - April 2026",
            "facts": [
                "Supported technical and community events with executives, volunteers, and attendees.",
                "Helped support a 24-hour event with 50+ participants.",
            ],
        },
    ],
    "projects": [
        {
            "name": "MalpariBot",
            "facts": [
                "Python algorithmic trading research platform with paper-only execution.",
                "Includes setup-based signal filtering, risk gates, PnL-after-fees reporting, structured logs, dashboards, dataset export, and ML-readiness reports.",
                "Has 500+ pytest tests.",
            ],
            "prohibited_claims": ["live trading", "profitable", "broker orders", "real-money deployment"],
        },
        {
            "name": "S.E.N.S.E.",
            "facts": [
                "Best Accessibility Hack winner and team-built smart glasses prototype.",
                "Used Python, Raspberry Pi, Arduino, Gemini API, and haptic feedback for voice-guided visually impaired micro-navigation.",
            ],
            "prohibited_claims": ["sole hardware owner", "production medical device"],
        },
        {
            "name": "JobApplier",
            "facts": ["Local-first job workflow automation, matching, tailoring, tracking, analytics, and human-review controls."],
            "prohibited_claims": ["blind auto-apply", "automatic submission"],
        },
    ],
    "resume_profiles": [
        "general_software", "web_frontend", "qa_testing", "data_reporting_bi",
        "fintech", "applied_ai_automation", "food_service_survival_job",
    ],
    "automation_level": 3,
}


def load_profile(path: str | None = None) -> Dict[str, Any]:
    """Load a private local override, falling back to the truthful built-in profile."""
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile_path = Path(path or Config.PROFILE_PATH)
    if profile_path.exists():
        try:
            with profile_path.open(encoding="utf-8") as handle:
                override = json.load(handle)
            if isinstance(override, dict):
                profile.update(override)
        except (OSError, json.JSONDecodeError):
            # A malformed private override must not replace the built-in source of truth.
            pass
    return profile


def save_profile(data: Dict[str, Any], path: str | None = None) -> Dict[str, Any]:
    """Merge and save profile settings locally; omitted private fields are preserved."""
    if not isinstance(data, dict):
        raise ValueError("Profile update must be a JSON object.")
    profile_path = Path(path or Config.PROFILE_PATH)
    profile = load_profile(str(profile_path))
    profile.update(data)
    try:
        profile["automation_level"] = min(4, max(0, int(profile.get("automation_level", 3))))
    except (TypeError, ValueError) as exc:
        raise ValueError("Automation level must be an integer from 0 through 4.") from exc
    if not isinstance(profile.get("skills"), list) or not all(isinstance(item, str) for item in profile["skills"]):
        raise ValueError("Skills must be a list of strings.")
    if not isinstance(profile.get("target_roles"), list) or not all(isinstance(item, str) for item in profile["target_roles"]):
        raise ValueError("Target roles must be a list of strings.")
    if not isinstance(profile.get("target_locations"), list) or not all(isinstance(item, str) for item in profile["target_locations"]):
        raise ValueError("Target locations must be a list of strings.")
    if data.get("graduation") and profile.get("education"):
        profile["education"][0]["expected_graduation"] = str(data["graduation"])
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = profile_path.with_suffix(profile_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2, ensure_ascii=True)
    os.replace(temporary, profile_path)
    return profile


def supported_claims(profile: Dict[str, Any] | None = None) -> list[str]:
    profile = profile or load_profile()
    claims = []
    for experience in profile.get("experience", []):
        claims.extend(experience.get("facts", []))
    for project in profile.get("projects", []):
        claims.extend(project.get("facts", []))
    return claims
