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
        "React", "React Native", "Expo", "Next.js", "Express.js", "FastAPI", "Flask", "Streamlit",
        "Pandas", "LightGBM", "PyTorch", "WebSockets", "Tailwind CSS", "Git", "GitHub", "Pull Requests",
        "Vercel", "SonarCloud", "GitGuardian", "Docker", "VS Code", "IntelliJ", "Linux", "macOS", "Windows",
        "Figma", "WordPress", "Elementor", "Pytest", "CI/CD", "CI/CD Checks",
        "Gemini API", "ElevenLabs API", "Binance API", "Yahoo Finance API", "Gmail API",
        "Raspberry Pi", "Arduino", "Frontend Development", "Software Testing", "Manual QA",
        "Regression Testing", "Bug Reporting", "API Integration", "Debugging",
        "Code Review", "Hardware-Software Integration", "Accessibility", "Version Control",
        "Data Processing", "Automation", "Risk Management", "Machine Learning",
    ],
    # Mirrors the current one-page resume (Mustafa_Alp_ARI_November.pdf). Tailoring only
    # reorders and selects from these entries; it never writes new claims. **text** is
    # bold on the rendered resume, as on the original.
    "resume": {
        "education": [{
            "institution": "York University", "location": "Toronto, ON",
            "degree": "BSc Honours in Computer Science, Minor in Economics", "dates": "Expected May 2029",
        }],
        "experience": [
            {
                "title": "Research Assistant", "company": "M4 & Aging Lab, York University",
                "dates": "Oct 2026 – Present", "location": "Toronto, ON",
                "bullets": [
                    "Updated the lab’s WordPress site with research articles, DOI links, PDFs, images, and Zoom recordings; reorganized publication cards and checked live links and page layouts.",
                ],
            },
            {
                "title": "Digital Strategy & Web Development Intern", "company": "Venture for Canada",
                "dates": "Jul 2026 – Aug 2026", "location": "Remote",
                "bullets": [
                    "Updated **5 WordPress/Elementor sites**, correcting navigation, contact details, and partner links; moved **23 demo pages and 6 placeholder portfolio items** out of public view.",
                    "Standardized **800+ organization records** for **14 partners**, delivering a consistent dataset for stakeholder outreach.",
                ],
            },
            {
                "title": "Software Developer Intern / Web Developer", "company": "Riipen Level UP",
                "dates": "May 2026 – Jul 2026", "location": "Remote",
                "bullets": [
                    "Rebuilt **Next.js/React navigation across 6 routes**, replacing the sidebar with **4 tabs and 2 secondary links** in a merged PR.",
                    "Cleared **SonarCloud duplication failures** by removing repeated Navbar code and obsolete sidebar components in a merged PR.",
                    "Fixed NBA Trade Machine validation around **$190M–$196M** using database-backed, season-specific thresholds through 2027/28; added null checks and verified changes in CI.",
                ],
            },
            {
                "title": "Software Development Project Contributor", "company": "Riipen Advance Ontario",
                "dates": "Apr 2026 – Jun 2026", "location": "Remote",
                "bullets": [
                    "Replaced mock marketplace, portfolio, and wallet data with API responses in a **Next.js/Express/MySQL** fintech app.",
                    "Tested borrower and admin workflows over **60 hours**; documented APIs, bugs, and smoke tests in a **348-line handoff**.",
                ],
            },
            {
                "title": "Software Developer Intern", "company": "Riipen Level UP",
                "dates": "Mar 2026 – May 2026", "location": "Remote",
                "bullets": [
                    "Built a **React Native sign-up screen** and merged beta UI updates, preserving existing login and password-reset flows while resolving conflicts across shared components.",
                ],
            },
        ],
        "projects": [
            {
                "name": "MalpariBot", "tech": "Python, LightGBM, PyTorch, pandas, pytest", "dates": "Oct 2025 – Present",
                "bullets": [
                    "Built a walk-forward ML research pipeline for **9 crypto futures pairs**, engineering **about 120 features** with purged splits, a sealed holdout, and tests for future-data leakage.",
                    "Developed paper-first execution, exchange reconciliation, scheduled retraining, and safe model swaps; maintained **about 900 automated tests** for trade safety and process control.",
                ],
            },
            {
                "name": "Lightning Response", "tech": "LightGBM, FastAPI, WebSockets", "dates": "Sep 2026",
                "bullets": [
                    "Co-built a real-time tyre-risk system using **127 F1 races, 138,683 laps, and 767K simulations**; reached **85% lock-up and 99% wheelspin early detection** on unseen drivers and won the **Ollon Motorsport Safety Track**.",
                ],
            },
            {
                "name": "S.E.N.S.E.", "tech": "Gemini API, ElevenLabs, WebSockets", "dates": "Feb 2026",
                "bullets": [
                    "Won **Best Accessibility Hack** with smart glasses combining Gemini visual guidance, ultrasonic obstacle detection, haptic alerts, and a live WebSocket caregiver dashboard.",
                ],
            },
        ],
        "leadership": [
            {
                "title": "Community Engagement Executive", "company": "CS Hub, York University | Previously VP Events (2025–2026)",
                "dates": "Sep 2026 – Present", "location": "Toronto, ON",
                "bullets": [
                    "Co-managed a **24-hour MLH-partnered hackathon** for **50+ attendees** in a **2,100+ member** student community, coordinating volunteers and live operations to keep the event on schedule.",
                ],
            },
        ],
        "skill_groups": [
            {"label": "Languages", "items": ["Python", "Java", "JavaScript", "TypeScript", "HTML", "CSS"]},
            {"label": "Frameworks & Libraries", "items": ["React", "React Native", "Next.js", "Express.js", "FastAPI", "LightGBM", "PyTorch", "pandas"]},
            {"label": "Tools & Platforms", "items": ["Git", "GitHub", "MySQL", "pytest", "CI/CD", "SonarCloud", "Vercel", "Figma", "WordPress"]},
        ],
    },
    "experience": [],
    "projects": [],
    "resume_profiles": [
        "general_software", "web_frontend", "qa_testing", "data_reporting_bi",
        "fintech", "applied_ai_automation", "food_service_survival_job",
    ],
    "automation_level": 3,
}


PROJECT_PROHIBITED_CLAIMS = {
    "MalpariBot": ["live trading", "profitable", "broker orders", "real-money deployment"],
    "S.E.N.S.E.": ["sole hardware owner", "production medical device"],
}


def _plain(text: str) -> str:
    return text.replace("**", "")


def _sync_facts_from_resume(profile: Dict[str, Any]) -> None:
    """Keep the flat experience/project fact lists in step with the structured resume."""
    resume = profile.get("resume") or {}
    profile["experience"] = [
        {"company": item["company"], "title": item["title"], "location": item.get("location", ""),
         "dates": item.get("dates", ""), "facts": [_plain(b) for b in item.get("bullets", [])]}
        for item in resume.get("experience", []) + resume.get("leadership", [])
    ]
    profile["projects"] = [
        {"name": item["name"], "tech": item.get("tech", ""), "dates": item.get("dates", ""),
         "facts": [_plain(b) for b in item.get("bullets", [])], "prohibited_claims": PROJECT_PROHIBITED_CLAIMS.get(item["name"], [])}
        for item in resume.get("projects", [])
    ]


_sync_facts_from_resume(DEFAULT_PROFILE)


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
                if "resume" in override and "experience" not in override:
                    _sync_facts_from_resume(profile)
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
