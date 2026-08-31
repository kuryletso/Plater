from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QFormLayout,
    QVBoxLayout,
)
from sqlalchemy.orm import Session

from app.gui.dialogs.widgets import (
    ErrorBanner,
    document_type_items,
    searchable_combo,
    selected_code,
    show_code,
)
from app.services.template.repository import TemplateRepository
from app.services.errors import ServiceError


class TemplateEditDialog(QDialog):
    """Edit Template's name, type, description etc.
    
    Languages are baked in and can't be edited.
    """

    def __init__(
            self,
            session: Session,
            template_id: int,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = TemplateRepository(session)
        self._template_id = template_id

        self.setWindowTitle("Edit template")
        self.setMinimumWidth(460)

        self.name_edit = QLineEdit()
        self.type_combo = searchable_combo(document_type_items(session))
        self.description_edit = QLineEdit()
        self.currency_check = QCheckBox("Append the currency to money values")
        self.languages_label = QLabel()
        self.languages_label.setEnabled(False)
        self.banner = ErrorBanner()

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("Name", self.name_edit)
        form.addRow("Document type", self.type_combo)
        form.addRow("Description", self.description_edit)
        form.addRow("Languages", self.languages_label)
        form.addRow("", self.currency_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(fields)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self._load()


    def _load(self) -> None:
        template = self._repo.get(self._template_id)
        config = self._repo.current_version(self._template_id).config

        self.name_edit.setText(template.name)
        show_code(self.type_combo, template.type)
        self.description_edit.setText(config.get("description") or "")
        self.currency_check.setChecked(bool(config.get("append_currency")))

        languages = " / ".join(
            code for code
            in (config.get("primary_language"), config.get("secondary_language"))
            if code
        )

        self.languages_label.setText(f"{languages} (re-import to change)")


    def _save(self) -> None:
        self.banner.clear_message()

        name = self.name_edit.text().strip()
        document_type = selected_code(self.type_combo)

        if not name or document_type is None:
            self.banner.show_message("Enter a name and select a document type.")
            return

        try:
            self._repo.update_metadata(
                self._template_id,
                name=name,
                document_type=document_type,
                description=self.description_edit.text().strip(),
                append_currency=self.currency_check.isChecked(),
            )
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.accept()