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
    show_code,
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
            bank_account_id: int | None = None,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = OrganizationRepository(session)
        self._organization_id = organization_id
        self.bank_account_id: int | None = None
        self._editing = bank_account_id

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

        if bank_account_id is None:
            self.localizations.set_values({ code: {} for code in default_languages(session) })
            return

        existing = next(
            (
                b for b in self._repo.get(organization_id).bank_accounts
                if b.id == bank_account_id
            ),
            None,
        )
        if existing is not None:
            self.iban_edit.setText(existing.iban)
            self.swift_edit.setText(existing.swift or "")
            show_code(self.currency_combo, existing.currency_code)
            show_code(self.country_combo, existing.country_code)
            self.localizations.set_values(
                {
                    code: {
                        "bank_name": row.bank_name or "",
                        "bank_info": row.bank_info or "",
                    } for code, row in existing.localizations.items()
                } or { code: {} for code in default_languages(session) }
            )


    def _save(self) -> None:
        self.banner.clear_message()

        iban = self.iban_edit.text().strip()
        swift = self.swift_edit.text().strip() or None
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
            if self._editing is not None:
                self._repo.update_bank_account(
                    self._organization_id,
                    self._editing,
                    iban=iban,
                    currency=currency,
                    swift=swift,
                    localizations=texts,
                )
                self.bank_account_id = self._editing
            else:
                self.bank_account_id = self._repo.add_bank_account(
                    self._organization_id,
                    iban=iban,
                    currency=currency,
                    country=country,
                    swift=swift,
                    localizations=texts or None,
                ).id
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.accept()