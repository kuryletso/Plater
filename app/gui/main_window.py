from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QFileDialog,
    QDialog,
)

from app.core.version import app_version
from app.paths import log_path
from app.db.session import SessionLocal

from app.gui.preview import PreviewPanel
from app.gui.widgets.collapsible_column import Accordion, CollapsibleColumn
from app.gui.dialogs.settings import SettingsDialog
from app.gui.dialogs.manager_dialog import ManagerDialog
from app.gui.dialogs.managers import (
    organization_asset,
    representative_asset,
    template_asset,
    measurement_unit_asset,
)
from app.gui.text import set_preferred_languages
from app.gui.settings import (
    display_languages,
    last_save_dir,
    set_window_geometry,
    window_geometry,
    set_last_save_dir,
)
from app.gui.columns.template_column import TemplateColumn
from app.gui.columns.party_column import PartyColumn, PartyRole
from app.gui.columns.document_column import DocumentColumn
from app.gui.draft_state import COLUMNS, DraftState, CLIENT, DOCUMENT, PROVIDER, TEMPLATE
from app.gui.i18n import error_text, diagnostic_text, severity_label

from app.services.doc_sequence.repository import SequenceRepository
from app.services.errors import ServiceError
from app.services.invoice.generate import InvoiceGenerateService, GenerationResult
from app.services.invoice.draft import InvoiceDraft
from app.services.invoice_line.repository import InvoiceLineRepository, InvoiceLineText
from app.services.template.rebuild_service import TemplateRebuildService

# chars, not supported by file systems in file name
_NOT_IN_FILE_NAMES = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def file_name(template: str | None, number: str) -> str:
    """Default {template}_{number}.docx. Not supported chars replaced with "_"."""

    stem = f"{template}_{number}" if template else number
    return f"{_NOT_IN_FILE_NAMES.sub('_', stem).strip(' .') or 'document'}.docx"        # Windows refuses name ending in dot


class MainWindow(QMainWindow):

    def __init__(self) -> None:

        self._session = SessionLocal()

        super().__init__()
        self.draft = DraftState(self)
        self.draft.changed.connect(self._refresh_readiness)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self.draft.changed.connect(self._preview_timer.start)

        self.setWindowTitle("Plater")
        self.resize(1280, 800)
        
        geometry = window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

        self._build_menu()

        self.preview = PreviewPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_workspace())
        splitter.addWidget(self.preview)
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

        for column in (
            self.template_column,
            self.provider_column,
            self.client_column,
        ):
            column.catalog_changed.connect(self._revalidate_columns)

        self._refresh_readiness()


    def closeEvent(self, event) -> None:
        set_window_geometry(self.saveGeometry())
        self._session.close()
        super().closeEvent(event)


    def offer_template_rebuilds(self) -> None:
        """Offers to rebuild the user's stale templates. 
        Called from main() after the window is shown, deliberately not from __init__: 
        a modal in a constructor blocks every headless test that builds a MainWindow.
        
        Built-in templates are rebuilt by the seeder without asking; 
        a user's own template is never rewritten without permission.
        """

        service = TemplateRebuildService(self._session)
        stale = service.stale(system=False)
        if not stale:
            return

        listed = "\n".join(f" \u2022 {template.name}" for template in stale[:10])
        if len(stale) > 10:
            listed += "\n " + self.tr("... and %n more", "", len(stale) - 10)

        answer = QMessageBox.question(
            self,
            self.tr("Rebuild templates?"),
            "\n\n".join((
                self.tr(
                    "%n template(s) were imported by an older version of the document engine:",
                    "",
                    len(stale),
                ),
                listed,
                self.tr(
                    "Rebuilding re-reads the stored source: names, languages and version " \
                    "histories stay, and only the engine's reading of the document is " \
                    "refreshed. Rebuild now?",
                ),
            )),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        failed = [
            outcome
            for outcome in (service.rebuild(template.id) for template in stale)
            if outcome.action != "rebuilt"
        ]
        self._revalidate_columns()

        if failed:
            QMessageBox.warning(
                self,
                self.tr("Some templates could not be rebuilt"),
                # Only 'rebuilt' have o.error as None, so they won't be present in failed;
                # following None check performed for static type checking
                "\n".join(f"{o.name}: {error_text(o.error) if o.error is not None else ''}" for o in failed),
            )


    def suggested_path(self, number: str) -> Path:
        """Returns either last save directory or default Documents."""

        folder = last_save_dir() or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
        return folder / file_name(self.draft.template_name, number)


    def _build_menu(self) -> None:
        """Every action should get its macOS role explicitly."""

        def add(menu, text, slot, role=QAction.MenuRole.NoRole) -> None:
            menu.addAction(text, slot).setMenuRole(role)

        file_menu = self.menuBar().addMenu(self.tr("&File"))
        add(file_menu, self.tr("E&xit"), self.close, QAction.MenuRole.QuitRole)

        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))
        add(edit_menu, self.tr("&Organizations..."), self._manage_organizations)
        add(edit_menu, self.tr("&Representatives..."), self._manage_representatives)
        add(edit_menu, self.tr("&Templates..."), self._manage_templates)
        edit_menu.addSeparator()
        add(edit_menu, self.tr("&Measurement units..."), self._manage_units)

        settings_menu = self.menuBar().addMenu(self.tr("&Settings"))
        add(settings_menu, self.tr("&Preferences..."), self._open_settings, QAction.MenuRole.PreferencesRole)

        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        add(help_menu, self.tr("Open &log folder"), self._open_log_folder)
        add(help_menu, self.tr("&About"), self._about, QAction.MenuRole.AboutRole)


    def _build_workspace(self) -> QWidget:
        self.template_column = TemplateColumn(self._session, self.draft)
        self.provider_column = PartyColumn(self._session, self.draft, PartyRole.PROVIDER)
        self.client_column = PartyColumn(self._session, self.draft, PartyRole.CLIENT)
        self.document_column = DocumentColumn(self._session, self.draft)

        self.accordion = Accordion()
        self._columns: dict[str, CollapsibleColumn] = {}

        contents = {
            TEMPLATE: (self.tr("Template"), self.template_column),
            PROVIDER: (self.tr("Provider"), self.provider_column),
            CLIENT: (self.tr("Client"), self.client_column),
            DOCUMENT: (self.tr("Document"), self.document_column),
        }
        for key in COLUMNS:
            title, content = contents[key]
            column = CollapsibleColumn(title, content)
            self._columns[key] = column
            self.accordion.add_column(column)

        workspace = QFrame()
        layout = QVBoxLayout(workspace)
        layout.addWidget(self.accordion, 1)

        return workspace


    def _build_footer(self) -> QWidget:
        self.generate_button = QPushButton(self.tr("Generate"))
        self.generate_button.clicked.connect(self._on_generate)
        self.generate_button.setEnabled(False)
        self.generate_button.setToolTip(self.tr("Finish document setup to generate"))

        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0,0,0,0)
        layout.addStretch(1)
        layout.addWidget(self.generate_button)

        return footer

    def _open_log_folder(self) -> None:
        """Packaged app has no console so the session log is the only source of test data."""

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path().parent)))


    def _about(self) -> None:
        QMessageBox.about(self, "Plater", self.tr("Plater {version} — invoice generator.").format(version=app_version()))


    def _refresh_readiness(self) -> None:
        for key, status in self.draft.statuses().items():
            self._columns[key].set_status(status)

        gaps = [ g for gaps in self.draft.missing_by_column().values() for g in gaps ]
        self.generate_button.setEnabled(not gaps)
        self.generate_button.setToolTip(
            self.tr("Ready to generate.") if not gaps else " | ".join(gaps) 
        )


    def _on_generate(self) -> None:
        draft = self.draft.to_draft()

        # peek only to name the file; the service runs its own peek/consume
        number = SequenceRepository(self._session).peek(draft.sequence_id)

        # ask before generating: cancelling here must not burn a number
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save document"),
            str(self.suggested_path(number.formatted)),
            self.tr("Word documents (*.docx)"),
        )
        if not chosen:
            return

        target = Path(chosen)
        set_last_save_dir(target.parent)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")

        try:
            result = InvoiceGenerateService(self._session).generate(draft)
        except ServiceError as error:
            QMessageBox.critical(
                self,
                self.tr("Generation failed"),
                error_text(error),
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
                self.tr("Could not save"),
                self.tr("Number {number} was issued, but the file could not be written:\n{error}").format(
                    number=result.number.formatted, error=error,
                ),
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
        primary = self.draft.languages[0] if self.draft.languages else None

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
                    primary=primary,
                )
            except ServiceError:
                self._session.rollback()


    def _report_failure(self, result: GenerationResult) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Generation failed"))
        box.setText(self.tr("The document could not be generated, so no number was used."))
        box.setDetailedText("\n".join(
            f"[{severity_label(item.severity)}] {item.code}: {diagnostic_text(item)}"
            for item in result.diagnostics.items
        ))
        box.exec()


    def _report_success(self, result: GenerationResult, target: Path) -> None:
        QMessageBox.information(
            self,
            self.tr("Document generated"),
            self.tr("Saved {number} to {file}.").format(
                number=result.number.formatted, file=target.name,
            ),
        )


    def _refresh_preview(self) -> None:
        """Must run preview() which renders without consuming a number."""

        if not self.draft.is_complete():
            self.preview.show_incomplete()
            return

        try:
            result = InvoiceGenerateService(self._session).preview(self.draft.to_draft())
        except ServiceError as e:
            self.preview.show_notice(error_text(e))
            return

        self.preview.show_result(result.number.formatted, result.diagnostics)


    def _manage_organizations(self) -> None:
        dialog = ManagerDialog(organization_asset(self._session), parent=self)
        dialog.exec()

        if dialog.changed:
            self._revalidate_columns()


    def _manage_representatives(self) -> None:
        dialog = ManagerDialog(representative_asset(self._session), parent=self)
        dialog.exec()

        if dialog.changed:
            self._revalidate_columns()


    def _manage_templates(self) -> None:
        dialog = ManagerDialog(template_asset(self._session), parent=self)
        dialog.exec()

        if dialog.changed:
            self._revalidate_columns()


    def _manage_units(self) -> None:
        dialog = ManagerDialog(measurement_unit_asset(self._session), parent=self)
        dialog.exec()

        if dialog.changed:
            self.document_column.reload_units()

    
    def _revalidate_columns(self) -> None:
        self.template_column.revalidate()
        self.provider_column.revalidate()
        self.client_column.revalidate()
        self.document_column.revalidate()


    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._session, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.language_changed:
            set_preferred_languages(display_languages())
            self._revalidate_columns()
            self.document_column.reload_units()