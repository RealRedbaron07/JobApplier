#!/usr/bin/env python3
"""Truth-constrained compatibility wrapper for cover-letter drafts.

The dashboard is the supported interface. This adapter remains for older local
imports, but it never calls an external model and never sends a draft.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from job_os.drafts import generate_application_answers
from job_os.profile import load_profile
from job_os.tailoring import validate_draft


class CoverLetterGenerator:
    def __init__(self) -> None:
        self.use_ai = False

    def generate_cover_letter(
        self,
        job: Dict,
        _user_profile: Dict | None = None,
        output_dir: str = "cover_letters",
    ) -> Tuple[str, str]:
        profile = load_profile()
        draft = generate_application_answers(job, profile)["cover_letter"]
        report = validate_draft(draft, profile)
        if not report["passed"]:
            raise ValueError(f"Draft failed claim validation: {report['violations']}")

        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        company = "".join(ch for ch in str(job.get("company") or "Company") if ch.isalnum() or ch in "-_")[:30]
        role = "".join(ch for ch in str(job.get("title") or "Role") if ch.isalnum() or ch in "-_")[:30]
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = target / f"{version}_{company}_{role}_DRAFT.txt"
        path.write_text("DRAFT — HUMAN REVIEW REQUIRED\n\n" + draft, encoding="utf-8")
        return draft, str(path)

