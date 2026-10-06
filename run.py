#!/usr/bin/env python3
"""
One command to run the whole GrandHeck demo:

    python run.py                 set up (first run only), build the dashboard, start the gateway
    python run.py --port 9000     use another port
    python run.py --no-browser    don't open a browser tab
    python run.py test            run the unit tests
    python run.py eval            run the evaluation (many simulated shifts) and write docs/results

First run creates .venv/, installs Python packages and builds the React dashboard.
After that it starts in a couple of seconds and needs no internet connection.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQS = BACKEND / "requirements.txt"
REQS_STAMP = VENV / ".requirements.sha1"


def say(msg: str) -> None:
    print(f"[run] {msg}", flush=True)


def ensure_python_env() -> None:
    if not VENV_PY.exists():
        say("creating virtual environment in .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    digest = hashlib.sha1(REQS.read_bytes()).hexdigest()
    if not REQS_STAMP.exists() or REQS_STAMP.read_text() != digest:
        say("installing Python packages ...")
        subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(REQS)])
        REQS_STAMP.write_text(digest)


def _newest_mtime(path: Path) -> float:
    return max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=0.0)


def ensure_frontend_built() -> None:
    dist = FRONTEND / "dist" / "index.html"
    sources = [FRONTEND / "src", FRONTEND / "index.html", FRONTEND / "package.json"]
    newest_src = max(_newest_mtime(s) if s.is_dir() else s.stat().st_mtime for s in sources)
    if dist.exists() and dist.stat().st_mtime >= newest_src:
        return
    npm = shutil.which("npm")
    if npm is None:
        if dist.exists():
            say("npm not found; using the existing (older) dashboard build")
            return
        sys.exit("[run] npm (Node.js 18+) is required to build the dashboard the first time.")
    if not (FRONTEND / "node_modules").exists():
        say("installing dashboard packages (npm install) ...")
        subprocess.check_call([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
    say("building dashboard ...")
    subprocess.check_call([npm, "run", "build"], cwd=FRONTEND)


def in_venv(*args: str) -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.call([str(VENV_PY), *args], cwd=BACKEND, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "test", "eval"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args, extra = parser.parse_known_args()

    ensure_python_env()
    if args.command == "test":
        sys.exit(in_venv("-m", "pytest", "-q", *extra))
    if args.command == "eval":
        sys.exit(in_venv("-m", "eval.evaluate", *extra))

    ensure_frontend_built()
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    say(f"GrandHeck gateway starting at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(2.0), webbrowser.open(url)), daemon=True).start()
    try:
        sys.exit(in_venv("-m", "uvicorn", "grandheck.api.server:app",
                         "--host", args.host, "--port", str(args.port), "--log-level", "warning"))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
