#!/usr/bin/env python3
"""Retired resume-to-profile importer.

Resume extraction can copy stale or ambiguous claims into a candidate profile.
The supported workflow is the dashboard's explicit, reviewable Settings form.
"""


def setup_profile(*_args, **_kwargs) -> bool:
    print("Automatic resume-to-profile import is retired to prevent unsupported claims.")
    print("Run: python3 run.py")
    print("Open Settings, review the configured facts, and save deliberate changes there.")
    return False


if __name__ == "__main__":
    setup_profile()

