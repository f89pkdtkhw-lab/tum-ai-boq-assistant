"""app.main must import from api/ with no PYTHONPATH (how uvicorn and render.yaml start it)."""
import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]


def test_main_imports_from_api_dir_without_pythonpath():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=API, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
