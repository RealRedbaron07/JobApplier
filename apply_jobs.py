#!/usr/bin/env python3
"""Deprecated application entry point.

JobApplier prepares drafts and checklists in the local dashboard. It never
opens protected application flows or submits an application.
"""

from __future__ import annotations


def apply_to_jobs() -> bool:
    print("Legacy application automation is disabled.")
    print("Run: python3 dashboard/app.py")
    print("Prepare and review a package there, submit on the official portal yourself,")
    print("then explicitly mark the job as applied in JobApplier.")
    return False


def apply_linkedin_job(*_args, **_kwargs) -> bool:
    """Compatibility stub: protected-board form automation is not permitted."""
    return False


if __name__ == "__main__":
    apply_to_jobs()
