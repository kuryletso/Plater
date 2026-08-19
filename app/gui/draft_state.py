from __future__ import annotations

from typing import cast

from datetime import date
from enum import StrEnum

from PySide6.QtCore import QObject, Signal

from app.services.invoice.draft import InvoiceDraft, PartySelection, LineInput

TEMPLATE = "Template"
PROVIDER = "Provider"
CLIENT = "Client"
DOCUMENT = "Document"
COLUMNS = (TEMPLATE, PROVIDER, CLIENT, DOCUMENT)


class ColumnStatus(StrEnum):
    PRISTINE = "pristine"       # untouched or still in progress
    COMPLETE = "complete"
    INVALID = "invalid"


class DraftState(QObject):
    """The user's selections.
    (!) Ids only, no ORM rows. Ther service re-validate
    everything at generate time; this only tracks selections.
    """

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.template_id: int | None = None
        self.document_type: str | None = None

        self.provider_organization_id: int | None = None
        self.provider_tax_id: int | None = None
        self.provider_representative_id: int | None = None
        self.provider_bank_id: int | None = None

        self.client_organization_id: int | None = None
        self.client_tax_id: int | None = None
        self.client_representative_id: int | None = None
        self.client_bank_id: int | None = None

        self.sequence_id: int | None = None
        self.lines: tuple[LineInput, ...] = ()
        self.currency_code: str | None = None
        self.issue_date: date = date.today()

        self._was_complete: set[str] = set()


    def set_template(
            self,
            template_id: int | None,
            document_type: str | None,
    ) -> None:
        
        if document_type != self.document_type:
            self.sequence_id = None

        self.template_id = template_id
        self.document_type = document_type
        self._emit()


    def set_provider_organization(self, organization_id: int | None) -> None:
        if organization_id != self.provider_organization_id:
            self.provider_tax_id = None
            self.provider_representative_id = None
            self.provider_bank_id = None
            self.sequence_id = None

        self.provider_organization_id = organization_id
        self._emit()


    def set_provider_tax(self, tax_id: int | None) -> None:
        self.provider_tax_id = tax_id
        self._emit()


    def set_provider_representative(self, representative_id: int | None) -> None:
        self.provider_representative_id = representative_id
        self._emit()


    def set_provider_bank(self, bank_account_id: int | None) -> None:
        self.provider_bank_id = bank_account_id
        self._emit()


    def set_client_organization(self, organization_id: int | None) -> None:
        if organization_id != self.client_organization_id:
            self.client_tax_id = None
            self.client_representative_id = None
            self.client_bank_id = None

        self.client_organization_id = organization_id
        self._emit()


    def set_client_tax(self, tax_id: int | None) -> None:
        self.client_tax_id = tax_id
        self._emit()


    def set_client_representative(self, representative_id: int | None) -> None:
        self.client_representative_id = representative_id
        self._emit()


    def set_client_bank(self, bank_account_id: int | None) -> None:
        self.client_bank_id = bank_account_id
        self._emit()


    def set_sequence(self, sequence_id: int | None) -> None:
        self.sequence_id = sequence_id
        self._emit()


    def set_lines(self, lines: tuple[LineInput, ...]) -> None:
        self.lines = lines
        self._emit()


    def set_currency(self, currency_code: str | None) -> None:
        self.currency_code = currency_code
        self._emit()


    def set_issue_date(self, issue_date: date) -> None:
        self.issue_date = issue_date
        self._emit()


    def missing_by_column(self) -> dict[str, list[str]]:
        missing: dict[str, list[str]] = {}

        if self.template_id is None:
            missing[TEMPLATE] = ["Select a template"]

        provider: list[str] = []
        if self.provider_organization_id is None:
            provider.append("Select a provider organization")
        elif self.provider_tax_id is None:
            provider.append("Select the provider's tax ID")
        if self.sequence_id is None:
            provider.append("Select a numbering sequence")
        if provider:
            missing[PROVIDER] = provider


        client: list[str] = []
        if self.client_organization_id is None:
            client.append("Select a client organization")
        elif self.client_tax_id is None:
            client.append("Select the client's tax ID")
        if client:
            missing[CLIENT] = client

        document: list[str] = []
        if not self.lines:
            document.append("Add at least one invoice line")
        if self.currency_code is None:
            document.append("Select a currency")
        if document:
            missing[DOCUMENT] = document

        return missing


    def statuses(self) -> dict[str, ColumnStatus]:
        missing = self.missing_by_column()

        return {
            column:
                ColumnStatus.COMPLETE if column not in missing
                else ColumnStatus.INVALID if column in self._was_complete
                else ColumnStatus.PRISTINE
            for column in COLUMNS
        }


    def is_complete(self) -> bool:
        return not self.missing_by_column()


    def to_draft(self) -> InvoiceDraft:
        assert self.is_complete()

        return InvoiceDraft(
            template_id=cast(int, self.template_id),        # self.is_complete() protects from None value
            sequence_id=cast(int, self.sequence_id),
            currency_code=cast(str, self.currency_code),
            issue_date=self.issue_date,
            provider=PartySelection(
                organization_id=cast(int, self.provider_organization_id),
                tax_id_id=cast(int, self.provider_tax_id),
                representative_id=self.provider_representative_id,
                bank_account_id=self.provider_bank_id,
            ),
            client=PartySelection(
                organization_id=cast(int, self.client_organization_id),
                tax_id_id=cast(int, self.client_tax_id),
                representative_id=self.client_representative_id,
                bank_account_id=self.client_bank_id,
            ),
            lines=self.lines,
        )


    def _emit(self) -> None:
        for column in COLUMNS:
            if column not in self.missing_by_column():
                self._was_complete.add(column)
        self.changed.emit()