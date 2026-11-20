"""Start the product locally: FastAPI backend on :8000 and Next.js UI on :3000.

    python tools/dev.py            # Start both, Ctrl+C stops both
    python tools/dev.py --install  # Install dependencies first (pip in .venv, npm in web/)

Keys come from .env.local in the repository root; without keys the model uses a mock.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NPM = shutil.which("npm") or "npm"


def install():
    if not PY.exists():
        made = subprocess.run([sys.executable, "-m", "venv", str(VENV)], capture_output=True, text=True)
        if made.returncode or not PY.exists():
            shutil.rmtree(VENV, ignore_errors=True)
            sys.exit("✗ Python cannot create a virtual environment. On Ubuntu/WSL run "
                     "`sudo apt install -y python3-venv` once, then rerun python3 tools/dev.py.")
    subprocess.run([str(PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "api" / "requirements.txt"),
                    "-r", str(ROOT / "api" / "requirements-dev.txt")], check=True)
    subprocess.run([NPM, "ci" if (ROOT / "web" / "package-lock.json").exists() else "install", "--no-audit", "--no-fund"],
                   cwd=ROOT / "web", check=True)


def pump(name, process, color):
    for line in iter(process.stdout.readline, ""):
        print(f"\033[{color}m{name:>4}\033[0m │ {line}", end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--install", action="store_true", help="install dependencies")
    args = parser.parse_args()
    if args.install or not PY.exists() or not (ROOT / "web" / "node_modules").exists():
        print("Installing dependencies …", flush=True)
        install()
    processes = [
        ("api", subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], cwd=ROOT / "api",
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"), "36"),
        ("web", subprocess.Popen([NPM, "run", "dev"], cwd=ROOT / "web", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace"), "35"),
    ]
    for name, process, color in processes:
        threading.Thread(target=pump, args=(name, process, color), daemon=True).start()
    print("Starting product: UI http://localhost:3000 · backend http://localhost:8000/health · Ctrl+C stops it", flush=True)
    try:
        while all(process.poll() is None for _, process, _ in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for _, process, _ in processes:
            if process.poll() is None:
                process.terminate()
        for _, process, _ in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()
