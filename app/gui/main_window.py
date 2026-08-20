from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QStandardPaths
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
    QFileDialog,
)

from app.gui.preview import PreviewPanel
from app.gui.widgets.collapsible_column import Accordion, CollapsibleColumn

from app.db.session import SessionLocal
from app.gui.columns.template_column import TemplateColumn
from app.gui.columns.party_column import PartyColumn, PartyRole
from app.gui.columns.document_column import DocumentColumn
from app.gui.draft_state import COLUMNS, DraftState

from app.core.errors import Severity
from app.services.doc_sequence.repository import SequenceRepository
from app.services.errors import ServiceError
from app.services.invoice.generate import InvoiceGenerateService, GenerationResult
from app.services.invoice.draft import InvoiceDraft
from app.services.invoice_line.repository import InvoiceLineRepository, InvoiceLineText


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
        self.provider_column = PartyColumn(self._session, self.draft, PartyRole.PROVIDER)
        self.client_column = PartyColumn(self._session, self.draft, PartyRole.CLIENT)
        self.document_column = DocumentColumn(self._session, self.draft)

        self.accordion = Accordion()
        self._columns: dict[str, CollapsibleColumn] = {}

        contents = {
            "Template": self.template_column,
            "Provider": self.provider_column,
            "Client": self.client_column,
            "Document": self.document_column,
        }
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
        self.generate_button.clicked.connect(self._on_generate)
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


    def _on_generate(self) -> None:
        draft = self.draft.to_draft()

        # peek only to name the file; the service runs its own peek/consume
        number = SequenceRepository(self._session).peek(draft.sequence_id)
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )

        # ask before generating: cancelling here must not burn a number
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Save document",
            str(Path(documents) / f"{number.formatted}.docx"),
            "Word documents (*.docx)",
        )
        if not chosen:
            return

        target = Path(chosen)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")

        try:
            result = InvoiceGenerateService(self._session).generate(draft)
        except ServiceError as error:
            QMessageBox.critical(
                self,
                "Generation failed",
                error.user_message or str(error),
            )
            return

        if result.docx is None:
            self._report_failure(result)
            return

        try:
            target.write_bytes(result.docx)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Could not save",
                f"Number {result.number.formatted} was issued, but the file "
                f"could not be written:\n{error}",
            )
            return

        self._remember_lines(draft)
        self.provider_column.refresh_sequences()
        self._report_success(result, target)


    def _remember_lines(self, draft: InvoiceDraft) -> None:
        """Feed the hint cache. A failure here must never look like a generation failure.
        The document is already on disk.
        """

        repository = InvoiceLineRepository(self._session)

        for line in draft.lines:
            try:
                repository.touch(
                    {
                        code: InvoiceLineText(description=text)
                        for code, text in line.descriptions.items()
                    },
                    quantity=line.quantity,
                    measurement_unit=line.unit_code,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                )
            except ServiceError:
                self._session.rollback()


    def _report_failure(self, result: GenerationResult) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Generation failed")
        box.setText("The document could not be generated, so no number was used.")
        box.setDetailedText("\n".join(
            f"[{item.severity}] {item.code}: {item.message}"
            for item in result.diagnostics.items
        ))
        box.exec()


    def _report_success(self, result: GenerationResult, target: Path) -> None:
        warnings = [
            item for item in result.diagnostics.items
            if item.severity == Severity.WARNING
        ]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Document generated")
        box.setText(f"Saved {result.number.formatted} to {target.name}.")

        if warnings:
            box.setInformativeText(
                f"{len(warnings)} warning(s) -- the document rendered, but see details."
            )
            box.setDetailedText("\n".join(
                f"{item.code}: {item.message}" for item in warnings
            ))

        box.exec()


    def closeEvent(self, event) -> None:
        self._session.close()
        super().closeEvent(event)