from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QLabel
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.document_engine.blueprint.models.template import TemplateConfig
from app.gui.dialogs.widgets import (
    ErrorBanner,
    document_type_items,
    language_items,
    searchable_combo,
    selected_code,
    show_code,
    default_languages,
    default_document_type,
)
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.template.import_service import TemplateImportService
from app.services.template.repository import TemplateRepository
from app.services.errors import ServiceError


class TemplateImportDialog(QDialog):
    def __init__(
            self,
            session: Session,
            template_id: int | None = None,     # adding new version to existing template if set, else creating new template
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._result = None
        self._service: TemplateImportService | None = None
        self.template_id: int | None = None
        self._template_id = template_id
        self.version: int | None = None

        self.setWindowTitle("Add template version" if template_id is not None else "Import template")
        self.setMinimumWidth(560)
        self.setAcceptDrops(True)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Browse a .docx template, or drop one here...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)

        self.inherited_label = QLabel()
        self.inherited_label.setEnabled(False)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0,0,0,0)
        file_layout.addWidget(self.path_edit, 1)
        file_layout.addWidget(browse)

        languages = language_items(session)
        defaults = default_languages(session)

        self.name_edit = QLineEdit()
        self.type_combo = searchable_combo(document_type_items(session))
        self.primary_combo = searchable_combo(languages)
        self.secondary_combo = searchable_combo([("", "(none)", ()), *languages])
        self.currency_check = QCheckBox("Append the currency to money value")
        self.description_edit = QLineEdit()

        show_code(self.primary_combo, defaults[0] if defaults else None)
        # show_code(self.secondary_combo, defaults[1] if len(defaults) > 1 else "")     # defaults secondary language to second default language
        show_code(self.secondary_combo, "")     # defaults secondary language to (none)
        show_code(self.type_combo, default_document_type(session))
        self.currency_check.setChecked(True)

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("File", file_row)
        form.addRow("Name", self.name_edit)
        form.addRow("Template", self.inherited_label)
        form.addRow("Document type", self.type_combo)
        form.addRow("Primary language", self.primary_combo)
        form.addRow("Secondary language", self.secondary_combo)
        form.addRow("Description", self.description_edit)
        form.addRow("", self.currency_check)

        self.diagnostics_list = QListWidget()
        self.banner = ErrorBanner()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        self._save_button().setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(fields)
        layout.addWidget(self.diagnostics_list, 1)
        layout.addWidget(self.banner)
        layout.addWidget(self.buttons)

        self.type_combo.currentIndexChanged.connect(self._reingest)
        self.primary_combo.currentIndexChanged.connect(self._reingest)
        self.secondary_combo.currentIndexChanged.connect(self._reingest)
        self.currency_check.toggled.connect(self._reingest)

        if template_id is None:
            form.setRowVisible(self.inherited_label, False)
        else:
            for widget in (
                self.name_edit,
                self.type_combo,
                self.primary_combo,
                self.secondary_combo,
                self.description_edit,
                self.currency_check,
            ):
                form.setRowVisible(widget, False)

            try:
                config = self._inherited_config(template_id)
            except ServiceError as e:
                self.banner.show_message(e.user_message or str(e))
                self.path_edit.setEnabled(False)
                return
            
            self.inherited_label.setText(
                f"{config.name} | {config.type} | "
                f"{' / '.join( c for c in (config.primary_language, config.secondary_language) if c )}"
            )


    def _save_button(self):
        return self.buttons.button(QDialogButtonBox.StandardButton.Save)


    def _browse(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select a template", "", "Word documents (*.docx)",
        )
        if chosen:
            self._use_file(Path(chosen))


    def _use_file(self, path: Path) -> None:
        self.path_edit.setText(str(path))
        if not self.name_edit.text().strip():
            self.name_edit.setText(path.stem)

        self._reingest()


    def _config(self) -> TemplateConfig | None:
        if self._template_id is not None:
            return self._inherited_config(self._template_id)
        
        else:
            primary = selected_code(self.primary_combo)
            document_type = selected_code(self.type_combo)
            if primary is None or document_type is None:
                return None

            return TemplateConfig(
                primary_language=primary,
                secondary_language=selected_code(self.secondary_combo) or None,
                type=document_type,
                name=self.name_edit.text().strip() or Path(self.path_edit.text()).stem,
                description=self.description_edit.text().strip(),
                append_currency=self.currency_check.isChecked(),
            )


    def _reingest(self) -> None:
        self._result = None
        self._service = None
        self._save_button().setEnabled(False)
        self.diagnostics_list.clear()
        self.banner.clear_message()

        path = self.path_edit.text().strip()
        try:
            config = self._config()
        except ServiceError as e:
            self.banner.show_message(e.user_message or str(e))
            return

        if not path or config is None:
            self.banner.show_message("Choose a document type and primary language.")
            return

        service = TemplateImportService(
            self._session,
            DbTemplateInputProvider(self._session, config),
        )

        try:
            result = service.ingest(Path(path))
        except AppError as e:
            self.banner.show_message(e.user_message or str(e))
            return

        for item in result.diagnostics.items:
            self.diagnostics_list.addItem(f"[{item.severity}] {item.code}: {item.message}")
        if not result.diagnostics.items:
            self.diagnostics_list.addItem("No issues found.")

        if result.diagnostics.has_errors:
            self.banner.show_message(
                "This template cannot be imported until the errors above are fixed."
            )
            return

        self._result = result
        self._service = service
        self._save_button().setEnabled(True)


    def _save(self) -> None:
        if self._result is None or self._service is None:
            return

        try:
            if self._template_id is not None:
                self.version = self._service.commit_version(
                    self._template_id, self._result,
                )
            else:
                self.template_id = self._service.commit(self._result)
        except AppError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.accept()


    def _inherited_config(self, template_id: int) -> TemplateConfig:
        """New version resolves against the same languages as the original, 
        so the config comes from the template rather than the form.
        """

        repository = TemplateRepository(self._session)
        template = repository.get(template_id)
        config = repository.current_version(template_id).config

        return TemplateConfig(
            primary_language=config["primary_language"],
            secondary_language=config.get("secondary_language"),
            type=template.type,
            name=template.name,
            description=config.get("description") or "",
            append_currency=bool(config.get("append_currency")),
        )


    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._dropped_docx(event.mimeData()) is not None:
            event.acceptProposedAction()


    def dropEvent(self, event: QDropEvent) -> None:
        path = self._dropped_docx(event.mimeData())
        if path is not None:
            event.acceptProposedAction()
            self._use_file(path)


    @staticmethod
    def _dropped_docx(mime) -> Path | None:
        """Only accepts local .docx, so the cursor says 'no' for anything else."""

        if not mime.hasUrls():
            return None

        for url in mime.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() == ".docx":
                    return path

        return None