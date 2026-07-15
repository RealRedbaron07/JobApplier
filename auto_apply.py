#!/usr/bin/env python3
"""Deprecated auto-apply entry point retained as an inert compatibility shim."""

from __future__ import annotations

from datetime import datetime, timezone


def scrape_jobs(*_args, **_kwargs) -> tuple[int, datetime]:
    """Return no jobs; protected-board scraping is deliberately disabled."""
    return 0, datetime.now(timezone.utc)


def apply_to_jobs(*_args, **_kwargs) -> tuple[int, int, int]:
    """Return submitted/manual/ready counts without taking external action."""
    return 0, 0, 0


def main(dry_run: bool = False) -> int:
    del dry_run
    print("Blind auto-apply and protected-board scraping are disabled.")
    print("Run: python3 dashboard/app.py")
    print("Use manual/pasted/CSV/JSON ingestion and review every draft before submitting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
