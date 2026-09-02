from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QGroupBox,
    QLineEdit,
)
from sqlalchemy.orm import Session

from app.gui.dialogs.widgets import (
    ErrorBanner,
    document_type_items,
    language_items,
    searchable_combo,
    selected_code,
    show_code,
)
from app.gui.settings import SUPPORTED_LANGUAGES, set_ui_language, ui_language
from app.services.errors import ServiceError
from app.services.settings import TemplateDefaultService

LANGUAGE_NAMES = {"ENG": "English", "UKR": "Українська"}


class SettingsDialog(QDialog):
    """Uses two different stores deliberately: 
    - interface preferences live in the ini file
    - template defaults live in the database
    """

    def __init__(
            self,
            session: Session,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._defaults = TemplateDefaultService(session)
        self._original_language = ui_language()
        self.language_changed = False

        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)

        self.language_combo = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(LANGUAGE_NAMES.get(code, code), code)

        interface = QGroupBox("Interface")
        interface_form = QFormLayout(interface)
        interface_form.addRow("Language", self.language_combo)

        languages = language_items(session)
        self.primary_combo = searchable_combo(languages)
        self.secondary_combo = searchable_combo([("", "(none)", ()), *languages])
        self.type_combo = searchable_combo(document_type_items(session))
        self.name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.currency_check = QCheckBox("Append the currency to money values")

        defaults = QGroupBox("New template defaults")
        defaults_form = QFormLayout(defaults)
        defaults_form.addRow("Primary language", self.primary_combo)
        defaults_form.addRow("Secondary language", self.secondary_combo)
        defaults_form.addRow("Document type", self.type_combo)
        defaults_form.addRow("Name", self.name_edit)
        defaults_form.addRow("Description", self.description_edit)
        defaults_form.addRow("", self.currency_check)

        self.banner = ErrorBanner()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(interface)
        layout.addWidget(defaults)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self._load()


    def _load(self) -> None:
        self.language_combo.setCurrentIndex(
            self.language_combo.findData(self._original_language)
        )

        row = self._defaults.get()
        show_code(self.primary_combo, row.primary_language_code)
        show_code(self.secondary_combo, row.secondary_language_code or "")
        show_code(self.type_combo, row.document_type_code)
        self.name_edit.setText(row.name)
        self.description_edit.setText(row.description or "")
        self.currency_check.setChecked(row.append_currency)


    def _save(self) -> None:
        self.banner.clear_message()

        primary = selected_code(self.primary_combo)
        document_type = selected_code(self.type_combo)

        if primary is None \
        or document_type is None \
        or not self.name_edit.text().strip():
            self.banner.show_message(
                "Primary language, document type and name required."
            )
            return

        try:
            self._defaults.update(
                primary_language=primary,
                secondary_language=selected_code(self.secondary_combo) or None,
                document_type=document_type,
                name=self.name_edit.text().strip(),
                description=self.description_edit.text().strip(),
                append_currency=self.currency_check.isChecked(),
            )
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        selected = self.language_combo.currentData()
        if selected != self._original_language:
            set_ui_language(selected)
            self.language_changed = True

        self.accept()