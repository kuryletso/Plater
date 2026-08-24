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
    ErrorBanner, LocalizedFields,
    country_items,
    currency_items,
    searchable_combo,
    selected_code,
    default_languages,
)
from app.services.organization.repository import BankText, OrganizationRepository
from app.services.errors import ServiceError


FIELDS = (
    ("bank_name", "Bank name"),
    ("bank_info", "Bank details"),
)

class BankAccountDialog(QDialog):
    """Add bank account to an organization. Its localized names are optional."""


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
        self.bank_account_id: int | None = None

        self.setWindowTitle("Add bank account")
        self.setMinimumWidth(460)

        self.iban_edit = QLineEdit()
        self.swift_edit = QLineEdit()
        self.currency_combo = searchable_combo(currency_items(session))
        self.country_combo = searchable_combo(country_items(session))
        self.localizations = LocalizedFields(session, FIELDS)
        self.banner = ErrorBanner()

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("IBAN", self.iban_edit)
        form.addRow("SWIFT", self.swift_edit)
        form.addRow("Currency", self.currency_combo)
        form.addRow("Country", self.country_combo)

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

        self.localizations.set_values({ code: {} for code in default_languages(session) })


    def _save(self) -> None:
        self.banner.clear_message()

        iban = self.iban_edit.text().strip()
        currency = selected_code(self.currency_combo)
        country = selected_code(self.country_combo)

        if not iban or currency is None or country is None:
            self.banner.show_message(
                "Enter an IBAN, selected currency and country.",
            )
            return

        texts = {
            code: BankText(
                bank_name=values.get("bank_name") or None,
                bank_info=values.get("bank_info") or None,
            )
            for code, values in self.localizations.values().items()
        }

        try:
            created = self._repo.add_bank_account(
                self._organization_id,
                iban=iban,
                currency=currency,
                country=country,
                swift=self.swift_edit.text().strip() or None,
                localizations=texts or None,
            )
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.bank_account_id = created.id
        self.accept()