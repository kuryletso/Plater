from __future__ import annotations

import sys
import logging
from PySide6.QtWidgets import QApplication


def main() -> int:
    from app.core.log import configure
    from app.paths import log_path

    configure(log_path())       # done first, so a failed migration is logged
    log = logging.getLogger("plater")
    log.info("Starting %s", _runtime())

    from app.db.session import init_db
    init_db()

    from app.gui.settings import display_languages
    from app.gui.text import set_preferred_languages
    set_preferred_languages(display_languages())

    app = QApplication(sys.argv)
    app.setApplicationName("Plater")
    app.setStyleSheet("""
            CollapsibleColumn {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4 px;
            }

            CollapsibleColumn[status="complete"] { border-color: #2e7d32; }

            CollapsibleColumn[status="invalid"]  { border-color: #c0392b; }

            QLineEdit[warn="true"] {
                background-color: #fff4d6;
                color: #1a1a1a;
                border: 1px solid #e0a800;
                border-radius: 2px;
                padding: 2px;
            }

            QLabel[role="error"] {
                background-color: #fdecea;
                color: #611a15;
                border: 1px solid #c0392b;
                border-radius: 3px;
                padding: 6px;
            }
        
            QLabel[role="warning"] {
                background-color: #fff4d6;
                color: #6b4e00;
                border: 1px solid #e0a800;
                border-radius: 3px;
                padding: 4px 8px;
            }
        """,
    )

    from app.gui.main_window import MainWindow
    window = MainWindow()
    window.show()
    window.offer_template_rebuilds()

    code = app.exec()
    log.info("Exiting with code %s", code)
    return code


def _version() -> str:
    """pyproject.toml is the version's one home. 
    Plater runs from source so there is no package metadata unless it was installed.
    """

    import tomllib
    from importlib import metadata

    from app.paths import PROJECT_ROOT

    try:
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as file:
            return tomllib.load(file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass

    try:
        return metadata.version("Plater")
    except metadata.PackageNotFoundError:
        return "unknown"


def _runtime() -> str:
    import platform
    import PySide6
    from app.document_engine.version import ENGINE_VERSION

    version = _version()
    return (
        f"Plater {version} | engine {ENGINE_VERSION} | Python {platform.python_version()} "
        f"| PySide {PySide6.__version__} | {platform.platform()}"
    )


if __name__ == "__main__":
    raise SystemExit(main())