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

from app.gui.dialogs.widgets import (
    ErrorBanner,
    country_items,
    searchable_combo,
    selected_code,
    tax_system_items,
)
from app.services.organization.repository import OrganizationRepository
from app.services.errors import ServiceError


class TaxIdDialog(QDialog):
    """Add a tax identifier to organization."""

    def __init__(
            self,
            session: Session,
            organization_id: int,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = OrganizationRepository(session)
        self._organization_id = organization_id
        self.tax_id_id: int | None = None

        self.setWindowTitle("Add Tax ID")
        self.setMinimumWidth(400)

        self.system_combo = searchable_combo(tax_system_items(session))
        self.country_combo = searchable_combo(country_items(session))
        self.value_edit = QLineEdit()
        self.banner = ErrorBanner()

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("System", self.system_combo)
        form.addRow("Country", self.country_combo)
        form.addRow("Number", self.value_edit)

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


    def _save(self) -> None:
        self.banner.clear_message()
        system = selected_code(self.system_combo)
        country = selected_code(self.country_combo)
        value = self.value_edit.text().strip()

        if system is None or country is None or not value:
            self.banner.show_message(
                "Select a system and country, enter the number."
            )
            return

        try:
            created = self._repo.add_tax_id(
                self._organization_id,
                tax_id_system=system,
                country=country,
                value=value,
            )
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.tax_id_id = created.id
        self.accept()