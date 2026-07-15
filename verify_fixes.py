#!/usr/bin/env python3
"""Compatibility verification command for the current local-first product."""

import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))
