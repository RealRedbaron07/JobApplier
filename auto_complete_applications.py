#!/usr/bin/env python3
"""Retired status-mutating compatibility command.

Job outcomes never become complete merely because time passed. Use dashboard
follow-up reminders and update each tracker status from verified information.
"""


def auto_complete_pending_applications(*_args, **_kwargs) -> int:
    print("Automatic status completion is disabled; no records were changed.")
    print("Use the dashboard's Follow-ups and Tracker views instead.")
    return 0


def check_pending_applications() -> int:
    print("Run: python3 run.py")
    print("The dashboard shows stale applications and due follow-ups without changing them.")
    return 0


if __name__ == "__main__":
    check_pending_applications()

