from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
)

from app.gui.preview import PreviewPanel
from app.gui.widgets.collapsible_column import Accordion, CollapsibleColumn

from app.db.session import SessionLocal
from app.gui.columns.template_column import TemplateColumn
from app.gui.draft_state import COLUMNS, DraftState


def _stub_content(title: str) -> QWidget:
    """Filler page until the real column content lands."""

    label = QLabel(f"{title} column")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setEnabled(False)

    page = QWidget()
    QVBoxLayout(page).addWidget(label)

    return page


class MainWindow(QMainWindow):

    def __init__(self) -> None:

        self._session = SessionLocal()

        super().__init__()
        self.draft = DraftState(self)
        self.draft.changed.connect(self._refresh_readiness)

        self.setWindowTitle("Plater")
        self.resize(1280, 800)

        self._build_menu()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_workspace())
        splitter.addWidget(PreviewPanel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6,6,6,6)
        layout.addWidget(splitter, 1)
        layout.addWidget(separator)
        layout.addWidget(self._build_footer())

        self.setCentralWidget(central)

        self._refresh_readiness()


    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("E&xit", self.close)

        settings_menu = self.menuBar().addMenu("&Settings")
        settings_menu.addAction("Template defaults...").setEnabled(False)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("&About", self._about)


    def _build_workspace(self) -> QWidget:
        self.template_column = TemplateColumn(self._session, self.draft)

        self.accordion = Accordion()
        self._columns: dict[str, CollapsibleColumn] = {}

        contents = {"Template": self.template_column}
        for title in COLUMNS:
            column = CollapsibleColumn(title, contents.get(title) or _stub_content(title))
            self._columns[title] = column
            self.accordion.add_column(column)

        workspace = QFrame()
        layout = QVBoxLayout(workspace)
        layout.addWidget(self.accordion, 1)

        return workspace


    def _build_footer(self) -> QWidget:
        self.generate_button = QPushButton("Generate")
        self.generate_button.setEnabled(False)
        self.generate_button.setToolTip("Finish document setup to generate")

        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0,0,0,0)
        layout.addStretch(1)
        layout.addWidget(self.generate_button)

        return footer


    def _about(self) -> None:
        QMessageBox.about(self, "Plater", "Plater — invoice generator.")


    def _refresh_readiness(self) -> None:
        for title, status in self.draft.statuses().items():
            self._columns[title].set_status(status)

        gaps = [ g for gaps in self.draft.missing_by_column().values() for g in gaps ]
        self.generate_button.setEnabled(not gaps)
        self.generate_button.setToolTip(
            "Ready to generate." if not gaps else " | ".join(gaps) 
        )


    def closeEvent(self, event) -> None:
        self._session.close()
        super().closeEvent(event)