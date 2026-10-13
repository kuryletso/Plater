"""Refresh the translation source in app/gui/translations from the code.

uv run python scripts/update_translations.py        # every plater_<language>.ts
uv run python scripts/update_translations.py uk     # also start plater_uk.ts

Run it after changing interface text, translate what is new in Qt Linguist 
(uv run pyside6-linguist app/gui/translations/plater_uk.ts). Then rerun scripts/build_ui.py 
to compile result. Text that is gone from the code is dropped from .ts . Git still keeps its history.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
DESIGNER_DIR = APP_DIR / "gui" / "designer"
GENERATED_DIR = APP_DIR / "gui" / "generated"
TRANSLATIONS_DIR = APP_DIR / "gui" / "translations"


def sources() -> list[Path]:
    """Every module and Designer form. The compiled forms are left out since lupdate 
    reads the .ui files themselves.
    """

    modules = [
        path for path in sorted(APP_DIR.rglob("*.py"))
        if GENERATED_DIR not in path.parents
    ]
    return [*modules, *sorted(DESIGNER_DIR.glob("*.ui"))]


def update(target: Path) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        listing = Path(scratch) / "sources.lst"     # too many files for a Windows command line
        listing.write_text("\n".join(str(path) for path in sources()), encoding="utf-8")

        subprocess.run(
            [
                "pyside6-lupdate", f"@{listing}", "-ts",
                str(target), "-locations", "relative", "-no-obsolete",
            ],
            check=True,
        )


def main(languages: list[str]) -> int:
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)

    targets = {*TRANSLATIONS_DIR.glob("plater_*.ts")}
    targets |= {TRANSLATIONS_DIR / f"plater_{language}.ts" for language in languages}

    for target in sorted(targets):
        update(target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))