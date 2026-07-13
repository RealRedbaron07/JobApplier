"""Truth-constrained resume tailoring plans and LaTeX draft generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from config import Config
from .profile import load_profile
from .scoring import choose_project, choose_resume_profile


PROFILE_PRIORITIES = {
    "general_software": ["Java", "Python", "JavaScript", "TypeScript", "Git", "Software Testing"],
    "web_frontend": ["TypeScript", "JavaScript", "React", "Next.js", "HTML", "CSS", "Tailwind CSS"],
    "qa_testing": ["Software Testing", "Manual QA", "Regression Testing", "Bug Reporting", "Pytest", "Debugging"],
    "data_reporting_bi": ["Python", "SQL", "MySQL", "Pandas", "Data Processing", "Automation"],
    "fintech": ["Python", "TypeScript", "Next.js", "MySQL", "Risk Management", "Data Processing"],
    "applied_ai_automation": ["Python", "Gemini API", "Automation", "API Integration", "Raspberry Pi", "Arduino"],
    "food_service_survival_job": ["Student leadership", "Team collaboration", "Events", "Customer support"],
}


PROHIBITED_PATTERNS = {
    "live_trading": r"\b(live trading|real[- ]money|broker orders?)\b",
    "profitability": r"\b(profitable|profitability|market[- ]beating)\b",
    "false_ownership": r"\b(single[- ]handedly|solely built|owned all hardware)\b",
    "automatic_submission": r"\b(blind auto[- ]apply|submitted applications automatically)\b",
}


def _latex_escape(value: str) -> str:
    substitutions = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    }
    return "".join(substitutions.get(character, character) for character in value)


def validate_draft(content: str, profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Reject known unsupported claims and unknown skill insertions."""
    profile = profile or load_profile()
    violations = []
    for code, pattern in PROHIBITED_PATTERNS.items():
        if re.search(pattern, content, re.I):
            violations.append({"code": code, "message": f"Unsupported or prohibited claim detected: {code}."})

    # Explicit experience-year claims are unsafe unless present in the factual profile.
    known_text = json.dumps(profile).lower()
    for years in re.findall(r"\b(\d+)\+? years?\b", content.lower()):
        phrase = f"{years} years"
        if phrase not in known_text:
            violations.append({"code": "unsupported_years", "message": f"Unsupported duration claim: {phrase}."})
    return {"passed": not violations, "violations": violations, "requires_human_review": True}


def create_tailoring_plan(job: Dict[str, Any], score: Dict[str, Any], profile: Dict[str, Any] | None = None, resume_profile: str | None = None) -> Dict[str, Any]:
    profile = profile or load_profile()
    selected_profile = resume_profile or score.get("resume_profile") or choose_resume_profile(job)
    priorities = PROFILE_PRIORITIES.get(selected_profile, PROFILE_PRIORITIES["general_software"])
    known = {skill.lower(): skill for skill in profile.get("skills", [])}
    matched = [known.get(skill.lower(), skill) for skill in score.get("matched_skills", []) if skill.lower() in known]
    skills_order = list(dict.fromkeys(matched + [skill for skill in priorities if skill.lower() in known]))
    project_name = score.get("project_to_emphasize") or choose_project(job)
    project = next((item for item in profile.get("projects", []) if item["name"] == project_name), profile["projects"][-1])

    experience_suggestions = []
    for experience in profile.get("experience", []):
        relevance = sum(1 for skill in skills_order if skill.lower() in json.dumps(experience).lower())
        if relevance or not experience_suggestions:
            experience_suggestions.append({
                "experience": f"{experience['title']} - {experience['company']}",
                "suggested_bullets": experience.get("facts", [])[:3],
                "instruction": "Select only bullets that directly support the posting; edit for concision without changing the factual meaning.",
            })

    plan = {
        "resume_profile": selected_profile,
        "skills_to_move_higher": skills_order,
        "keyword_gaps": score.get("missing_skills", []),
        "keyword_gap_rule": "Missing skills are gaps to learn or discuss honestly, never keywords to insert as owned skills.",
        "project_to_emphasize": {"name": project["name"], "bullets": project.get("facts", [])},
        "experience_suggestions": experience_suggestions[:3],
        "one_page_check": {"estimated_lines": 46 + len(skills_order), "limit": 58, "passes_estimate": 46 + len(skills_order) <= 58},
        "base_resume_warning": "The inspected base PDF says Expected May 2028; the configured truthful default is May 2029. Verify before exporting a final resume.",
        "review_status": "draft",
    }
    latex = generate_latex_draft(job, plan, profile)
    plan["latex"] = latex
    plan["safety_report"] = validate_draft(latex, profile)
    return plan


def generate_latex_draft(job: Dict[str, Any], plan: Dict[str, Any], profile: Dict[str, Any]) -> str:
    """Create an editable one-page-oriented LaTeX source draft from approved facts."""
    experiences = []
    for suggestion in plan.get("experience_suggestions", [])[:3]:
        bullets = "\n".join(f"\\item {_latex_escape(bullet)}" for bullet in suggestion["suggested_bullets"][:2])
        experiences.append(f"\\textbf{{{_latex_escape(suggestion['experience'])}}}\n\\begin{{itemize}}[leftmargin=*,nosep]\n{bullets}\n\\end{{itemize}}")
    project = plan["project_to_emphasize"]
    project_bullets = "\n".join(f"\\item {_latex_escape(bullet)}" for bullet in project["bullets"][:2])
    return f"""% DRAFT - HUMAN REVIEW REQUIRED. Generated only from the configured factual profile.
\\documentclass[10pt,letterpaper]{{article}}
\\usepackage[margin=0.58in]{{geometry}}
\\usepackage{{enumitem,hyperref}}
\\pagestyle{{empty}}
\\begin{{document}}
\\begin{{center}}
{{\\Large \\textbf{{{_latex_escape(profile['name'])}}}}}\\\\
{_latex_escape(profile['phone'])} $|$ {_latex_escape(profile['email'])} $|$ {_latex_escape(profile['linkedin'])} $|$ {_latex_escape(profile['github'])}
\\end{{center}}
\\section*{{Education}}
\\textbf{{York University}} - BSc Honours Computer Science, Minor in Economics \\hfill Expected {_latex_escape(profile['graduation'])}
\\section*{{Relevant Experience}}
{chr(10).join(experiences)}
\\section*{{Selected Project}}
\\textbf{{{_latex_escape(project['name'])}}}
\\begin{{itemize}}[leftmargin=*,nosep]
{project_bullets}
\\end{{itemize}}
\\section*{{Technical Skills}}
{_latex_escape(', '.join(plan['skills_to_move_higher']))}
\\vfill
\\footnotesize Draft targeted to {_latex_escape(job.get('title', 'the role'))} at {_latex_escape(job.get('company', 'the company'))}. Review every line before use.
\\end{{document}}
"""


def save_latex_draft(job_id: int, latex: str, directory: str | None = None) -> str:
    target_dir = Path(directory or Config.DRAFTS_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"job_{job_id}_resume_draft.tex"
    path.write_text(latex, encoding="utf-8")
    return str(path)
