from __future__ import annotations

from typing import cast

from datetime import date
from enum import StrEnum
from dataclasses import dataclass, field
from decimal import Decimal

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


@dataclass(slots=True)
class LineRow:
    """One grid row, possibly mid-typing. Untouched numeric cells are None,
    never 0 — a fresh row must not read as 'quantity is invalid'.
    """

    descriptions: dict[str, str] = field(default_factory=dict)
    unit_code: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None


    def is_blank(self) -> bool:
        """Blank rows are workspace, not errors, including the one we start with."""

        return (
            not any( text.strip() for text in self.descriptions.values())
            and self.unit_code is None
            and self.quantity is None
            and self.unit_price is None
            and self.tax_rate is None
        )

    def problems(self, primary_language: str) -> list[str]:
        gaps: list[str] = []
        if not self.descriptions.get(primary_language, "").strip():
            gaps.append("description")
        if self.unit_code is None:
            gaps.append("unit")
        if self.quantity is None or self.quantity <= 0:
            gaps.append("quantity")
        if self.unit_price is None or self.unit_price < 0:
            gaps.append("price")
        return gaps

    def to_input(self) -> LineInput:
        """Only meaningful for rows with no problems(), to_draft() guards that."""

        return LineInput(
            descriptions={
                code: text.strip()
                for code, text in self.descriptions.items()
                if text.strip()
            },
            unit_code=cast(str, self.unit_code),
            quantity=cast(Decimal, self.quantity),
            unit_price=cast(Decimal, self.unit_price),
            tax_rate=self.tax_rate if self.tax_rate is not None else Decimal(0),
        )


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
        self.languages: tuple[str, ...] = ()
        self.rows: tuple[LineRow, ...] = ()
        self.currency_code: str | None = None
        self.issue_date: date = date.today()

        self._was_complete: set[str] = set()


    def set_template(
            self,
            template_id: int | None,
            document_type: str | None,
            languages: tuple[str, ...],
    ) -> None:
        
        if document_type != self.document_type:
            self.sequence_id = None

        self.template_id = template_id
        self.document_type = document_type
        self.languages = languages
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


    def set_rows(self, rows: tuple[LineRow, ...]) -> None:
        self.rows = rows
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
        primary = self.languages[0] if self.languages else None

        if all( row.is_blank() for row in self.rows ):
            document.append("Add at least one invoice line")
        elif primary is not None:
            for number, row in enumerate(self.rows, start=1):
                if row.is_blank():
                    continue
                if gaps := row.problems(primary):
                    document.append(f"Line {number}: {' and '.join(gaps)} required")
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
            lines=tuple(
                row.to_input() for row in self.rows if not row.is_blank()
            ),
        )


    def warning(self) -> list[str]:
        """Warns about non-critical issues, doesn't block generation."""

        out: list[str] = []

        if (
            self.provider_organization_id is not None
            and self.provider_organization_id == self.client_organization_id
        ):
            out.append("Provider and client are the same organization.")

        return out


    def _emit(self) -> None:
        for column in COLUMNS:
            if column not in self.missing_by_column():
                self._was_complete.add(column)
        self.changed.emit()