from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication


def main() -> int:
    from app.db.session import init_db
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("Plater")
    app.setStyleSheet("""
            CollapsibleColumn {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4 px;
            }
            CollapsibleColumn[status="complete"] { border-color: #2e7d32; }
            CollapsibleColumn[status="invalid"] { border-color: #c0392b; }

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
        """,
    )

    from app.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())