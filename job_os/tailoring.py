"""Truth-constrained resume tailoring plans and LaTeX draft generation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from config import Config
from .parser import extract_skills
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

UNSAFE_LATEX_PATTERN = re.compile(
    r"\\(?:write18|write|immediate|input|include|openin|openout|read|catcode|csname|special|directlua)\b",
    re.I,
)


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

    known_skills = {skill.lower() for skill in profile.get("skills", [])}
    for skill in extract_skills(content):
        claim_context = re.compile(
            rf"(?:expert in|proficient in|skilled in|knowledge of|experience (?:with|using)|worked (?:with|using)|tools including|technical skills)[^.]{{0,220}}\b{re.escape(skill)}\b",
            re.I,
        )
        if skill.lower() not in known_skills and claim_context.search(content):
            violations.append({"code": "unsupported_skill", "message": f"Unsupported skill claim detected: {skill}."})

    # Catch arbitrary technology names that are not yet part of the parser's
    # finite catalog when the draft makes an explicit skill-ownership claim.
    for match in re.finditer(
        r"\b(?:expert in|proficient in|skilled in|tools including|technical skills(?: include|:))\s+([^;\n]{1,220})",
        content,
        re.I,
    ):
        fragment = re.split(r"\.(?=\s+[A-Z])|\\n", match.group(1), maxsplit=1)[0]
        for raw_claim in re.split(r",|/|\band\b", fragment, flags=re.I):
            claimed = re.sub(r"^(?:the|a|an)\s+", "", raw_claim.strip(" .:-()"), flags=re.I)
            if not claimed or len(claimed.split()) > 4 or claimed.lower() in known_skills:
                continue
            violations.append({"code": "unsupported_skill", "message": f"Unsupported explicit skill claim detected: {claimed}."})

    if re.search(r"\b(?:gpa|cgpa|grade point average)\b", content, re.I) and not re.search(r"\b(?:gpa|cgpa|grade point average)\b", json.dumps(profile), re.I):
        violations.append({"code": "unsupported_gpa", "message": "A GPA claim is not present in the configured factual profile."})

    configured_graduation = re.search(r"20\d{2}", str(profile.get("graduation", "")))
    for claimed in re.findall(r"(?:expected|graduat(?:e|ing|ion))[^\d]{0,25}(20\d{2})", content, re.I):
        if configured_graduation and claimed != configured_graduation.group():
            violations.append({"code": "graduation_mismatch", "message": f"Draft graduation year {claimed} does not match configured {configured_graduation.group()}."})

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
        "base_resume_warning": f"The inspected base PDF says Expected May 2028; the currently configured value is {profile.get('graduation', 'not set')}. Verify before exporting a final resume.",
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
    education = (profile.get("education") or [{}])[0]
    institution = education.get("institution") or "Education institution not configured"
    degree = education.get("degree") or "Degree not configured"
    minor = education.get("minor")
    education_label = f"{degree}, Minor in {minor}" if minor else degree
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
\\textbf{{{_latex_escape(institution)}}} - {_latex_escape(education_label)} \\hfill Expected {_latex_escape(str(profile.get('graduation') or education.get('expected_graduation') or 'Confirm date'))}
\\section*{{Relevant Experience}}
{chr(10).join(experiences)}
\\section*{{Selected Project}}
\\textbf{{{_latex_escape(project['name'])}}}
\\begin{{itemize}}[leftmargin=*,nosep]
{project_bullets}
\\end{{itemize}}
\\section*{{Technical Skills}}
{_latex_escape(', '.join(plan['skills_to_move_higher']))}
\\end{{document}}
"""


def save_latex_draft(job_id: int, latex: str, directory: str | None = None) -> str:
    if not isinstance(latex, str) or len(latex.encode("utf-8")) > 1_000_000:
        raise ValueError("LaTeX draft must be UTF-8 text no larger than 1 MB.")
    if UNSAFE_LATEX_PATTERN.search(latex):
        raise ValueError("LaTeX draft contains a file, shell, or interpreter command that JobApplier will not save.")
    target_dir = Path(directory or Config.DRAFTS_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = target_dir / f"job_{job_id}_resume_draft_{version}.tex"
    path.write_text(latex, encoding="utf-8")
    return str(path)
