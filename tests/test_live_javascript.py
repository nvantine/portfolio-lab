from pathlib import Path
import shutil
import subprocess
import pytest


def test_live_page_polling_and_preserved_inputs():
    if not shutil.which("node"): pytest.skip("Node is required for JavaScript behavior checks")
    root = Path(__file__).resolve().parent.parent
    for source in ("portfolio/static/portfolio/live.js", "portfolio/static/portfolio/lab.js"):
        subprocess.run(["node", "--check", source], cwd=root, check=True, capture_output=True)
    result = subprocess.run(["node", "tests/live_page_checks.cjs"], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
