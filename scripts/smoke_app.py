"""Starts the built app, no window, then checks what it logs.
Usage: uv run python scripts/smoke_app.py [path/to/Plater.exe]

The app gets a fresh database, log and settings (Ukrainian interface) in a temporary folder. 
Within the time limit it must log its version, run every migration, create every built-in template and 
switch to Ukrainian, then keep running, with no warning, error or unhandled exception on the way. 
Missing Qt translation is a warning too.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP = PROJECT_ROOT / "dist" / (
    "Plater.app/Contents/MacOS/Plater" if sys.platform == "darwin"
    else "Plater/Plater.exe"
)
TIMEOUT = 90
SETTLE = 5
LANGUAGE_SET = "Interface language UKR"
TROUBLE = re.compile(r"^\S+ \S+ (WARNING|ERROR|CRITICAL)\b")


def expected() -> tuple[str, int, int]:
    """This version, the number of migrations and the number of built-in templates."""

    with open(PROJECT_ROOT / "pyproject.toml", "rb") as file:
        version = tomllib.load(file)["project"]["version"]
    migrations = len(list((PROJECT_ROOT / "alembic" / "versions").glob("*.py")))
    manifest = PROJECT_ROOT / "app" / "db" / "seed_data" / "templates.json"
    built_ins = len(json.loads(manifest.read_text(encoding="utf-8")))
    return version, migrations, built_ins


def read(log: Path) -> str:
    return log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""


def run(app: Path) -> tuple[str, bool]:
    """The app's log, and whether it was still running at the end."""

    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        log = folder / "plater.log"
        (folder / "plater.ini").write_text("[ui]\nlanguage=UKR\n", encoding="utf-8")
        environment = {
            **os.environ,
            "PLATER_DB": str(folder / "plater.db"),
            "PLATER_LOG": str(log),
            "PLATER_SETTINGS": str(folder / "plater.ini"),
            "QT_QPA_PLATFORM": "offscreen",
        }

        process = subprocess.Popen([str(app)], env=environment)
        try:
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline and process.poll() is None:
                if LANGUAGE_SET in read(log):
                    time.sleep(SETTLE)
                    break
                time.sleep(0.5)
            running = process.poll() is None
        finally:
            process.terminate()
            process.wait(timeout=30)

        return read(log), running


def main() -> int:
    app = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_APP
    if not app.is_file():
        print(f"No app at {app}: build it with scripts/build_app.py")
        return 1

    version, migrations, built_ins = expected()
    text, running = run(app)

    problems = []
    if f"Starting Plater {version} |" not in text:
        problems.append(f"it did not log starting version {version}")
    if (count := text.count("Running upgrade")) != migrations:
        problems.append(f"it ran {count} of {migrations} migrations")
    if (count := len(re.findall(r"built-in \S+ created", text))) != built_ins:
        problems.append(f"it created {count} of {built_ins} built-in templates")
    if LANGUAGE_SET not in text:
        problems.append(f"it did not switch to Ukrainian within {TIMEOUT} s")
    if not running:
        problems.append("it exited by itself")
    problems += [f"it logged: {line}" for line in text.splitlines() if TROUBLE.search(line)]

    if problems:
        print(f"Smoke test FAILED for {app}:")
        print("\n".join(f" - {problem}" for problem in problems))
        print("\nIts log:\n" + (text or "(empty)"))
        return 1

    print(f"Smoke test passed: Plater {version} started, ran {migrations} migrations, "
          f"created {built_ins} built-in templates and switched to Ukrainian.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
