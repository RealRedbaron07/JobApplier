#!/usr/bin/env python3
"""Retired compatibility entry point for the old application export script.

The maintained exporter lives in the local dashboard and uses the current
tracker schema. Keeping this file inert prevents older shortcuts from reading
columns that no longer exist or creating misleading partial exports.
"""


def export_to_csv(_output_file: str | None = None) -> bool:
    """Point callers to the maintained dashboard export without writing data."""
    print("Run 'python3 run.py', open Application Tracker, and choose Export CSV.")
    return False


def export_summary_table() -> bool:
    """Point callers to the maintained analytics summary export."""
    print("Run 'python3 run.py', open Application Tracker, and choose Export Summary.")
    return False


if __name__ == "__main__":
    export_to_csv()
