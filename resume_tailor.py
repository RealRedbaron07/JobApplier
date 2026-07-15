#!/usr/bin/env python3
"""Truth-constrained compatibility wrapper for LaTeX resume drafts."""

from pathlib import Path
from typing import Dict

from job_os.parser import parse_job_description
from job_os.profile import load_profile
from job_os.scoring import score_job
from job_os.tailoring import create_tailoring_plan, save_latex_draft


class ResumeTailor:
    """Create a new editable LaTeX draft without modifying the source resume."""

    def __init__(self) -> None:
        self.use_ai = False
        self.client = None

    def tailor_resume(
        self,
        original_resume_path: str,
        job: Dict,
        _user_profile: Dict | None = None,
        output_dir: str = "tailored_resumes",
    ) -> str:
        source = Path(original_resume_path)
        if not source.is_file():
            raise FileNotFoundError(f"Resume not found: {source}")
        profile = load_profile()
        parsed = parse_job_description(str(job.get("description") or ""), job)
        scoring = score_job(parsed, profile)
        plan = create_tailoring_plan(parsed, scoring, profile)
        if not plan["safety_report"]["passed"]:
            raise ValueError(f"Draft failed claim validation: {plan['safety_report']['violations']}")
        return save_latex_draft(int(job.get("id") or 0), plan["latex"], output_dir)


if __name__ == "__main__":
    print("Use the dashboard's Resume Tailor view: python3 run.py")
