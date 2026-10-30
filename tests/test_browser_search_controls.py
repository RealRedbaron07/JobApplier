from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for the browser control checks")
def test_search_click_behavior_without_external_services():
    script = Path(__file__).with_name("browser_search_controls.cjs")
    result = subprocess.run(["node", "--test", str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
