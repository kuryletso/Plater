from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication


def main() -> int:
    from app.db.session import init_db
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("Plater")
    app.setStyleSheet(
        'CollapsibleColumn[status="invalid"] { border: 1px solid #c0392b; }',
    )

    from app.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())