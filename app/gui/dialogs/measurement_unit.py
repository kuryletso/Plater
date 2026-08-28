from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)
from sqlalchemy.orm import Session

from app.gui.dialogs.widgets import ErrorBanner, LocalizedFields, default_languages
from app.services.errors import ServiceError
from app.services.measurement_unit.repository import MeasurementUnitRepository, MeasurementUnitText

FIELDS = (("name", "Name"),)


class MeasurementUnitDialog(QDialog):
    """Register user added unit beside seeded ones."""

    def __init__(
            self,
            session: Session,
            code: str = "",
            unit_code: str | None = None,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = MeasurementUnitRepository(session)
        self.unit_code: str | None = None
        self._editing = unit_code

        self.setWindowTitle("Edit measurement unit" if unit_code else "New measurement unit")
        self.setMinimumWidth(420)

        self.code_edit = QLineEdit(code)
        self.code_edit.setPlaceholderText("hour")
        self.localizations = LocalizedFields(session, FIELDS)
        self.banner = ErrorBanner()

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("Code", self.code_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(fields)
        layout.addWidget(self.localizations)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        if unit_code is None:
            self.localizations.set_values({ lang: {} for lang in default_languages(session) })
            return


        existing = self._repo.get(unit_code)
        self.code_edit.setText(existing.code)
        self.code_edit.setEnabled(False)
        self.localizations.set_values({
            language: {"name": row.name}
            for language, row in existing.localizations.items()
        })


    def _save(self) -> None:
        self.banner.clear_message()

        texts: dict[str, MeasurementUnitText] = {}
        for code, value in self.localizations.values().items():
            texts[code] = MeasurementUnitText(name=value["name"])

        if not texts:
            self.banner.show_message("Enter the unit name in at least one language.")
            return

        try:
            if self._editing is not None:
                changed = self._repo.update(self._editing, texts)
            else:
                changed = self._repo.create(self.code_edit.text(), texts)
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.unit_code = changed.code
        self.accept()
