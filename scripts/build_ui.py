"""Compile every Designer .ui under app/gui/designer into app/gui/generated.

uv run python scripts/build_ui.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGNER_DIR = PROJECT_ROOT / "app" / "gui" / "designer"
GENERATED_DIR = PROJECT_ROOT / "app" / "gui" / "generated"


def main() -> int:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    for source in sorted(DESIGNER_DIR.glob("*.ui")):
        target = GENERATED_DIR / f"ui_{source.stem}.py"
        print(f"{source.relative_to(PROJECT_ROOT)} -> {target.relative_to(PROJECT_ROOT)}")
        subprocess.run(["pyside6-uic", str(source), "-o", str(target)], check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())