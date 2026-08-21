from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.configs.default_template_config import DefaultTemplateConfig
from app.gui.dialogs.widgets import ErrorBanner, LocalizedFields
from app.services.errors import ServiceError
from app.services.organization.repository import OrganizationRepository, OrganizationText

FIELDS = (
    ("org_type", "Legal form"),
    ("legal_name", "Legal name"),
    ("address", "Address"),
)


class OrganizationDialog(QDialog):
    """Create or edit an organization. Tax IDs, banks and representative entities 
    are added separately.
    """

    def __init__(
            self,
            session: Session,
            organization_id: int | None = None,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = OrganizationRepository(session)
        self.organization_id = organization_id

        self.setWindowTitle("Edit organization" if organization_id else "New organization")
        self.setMinimumWidth(460)

        self.localizations = LocalizedFields(session, FIELDS)
        self.email_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.banner = ErrorBanner()

        contacts = QWidget()
        form = QFormLayout(contacts)
        form.setContentsMargins(0,0,0,0)
        form.addRow("Email", self.email_edit)
        form.addRow("Phone", self.phone_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.localizations)
        layout.addWidget(contacts)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self._load()


    def _load(self) -> None:
        if self.organization_id is None:
            self.localizations.set_values({
                code: {} for code in self._default_languages()
            })
            return

        organization = self._repo.get(self.organization_id)
        self.email_edit.setText(organization.email or "")
        self.phone_edit.setText(organization.phone or "")
        self.localizations.set_values({
            code: {
                "org_type": row.org_type,
                "legal_name": row.legal_name,
                "address": row.address or "",
            }
            for code, row in organization.localizations.items()
        })


    def _default_languages(self) -> tuple[str, ...]:
        config = self._session.scalars(select(DefaultTemplateConfig)).first()
        if config is None:
            return ("ENG",)

        return tuple(
            code for code
            in (
                config.primary_language_code,
                config.secondary_language_code,
            ) if code
        )


    def _save(self) -> None:
        self.banner.clear_message()

        texts: dict[str, OrganizationText] = {}
        for code, values in self.localizations.values().items():
            if not values.get("org_type") or not values.get("legal_name"):
                self.banner.show_message(
                    f"{self.localizations.language_name(code)}: "
                    f"legal from and name are both required."
                )
                return

            texts[code] = OrganizationText(
                org_type=values["org_type"],
                legal_name=values["legal_name"],
                address=values.get("address") or None,
            )

        if not texts:
            self.banner.show_message(
                "Enter the legal form and name in at least one language."
            )
            return

        email = self.email_edit.text().strip() or None
        phone = self.phone_edit.text().strip() or None

        try:
            if self.organization_id is None:
                created = self._repo.create(texts, email=email, phone=phone)
                self.organization_id = created.id
            else:
                self._repo.update(
                    self.organization_id,
                    localizations=texts, email=email, phone=phone,
                )
        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.accept()