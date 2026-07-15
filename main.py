#!/usr/bin/env python3
"""Start the local JobApplier dashboard."""

from __future__ import annotations

from config import Config
from dashboard.app import app


def main() -> None:
    if Config.DASHBOARD_HOST not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("DASHBOARD_HOST must be loopback-only unless authentication is added.")
    print(f"JobApplier: http://{Config.DASHBOARD_HOST}:{Config.DASHBOARD_PORT}")
    print("Local-first. Nothing is submitted automatically.")
    app.run(host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
