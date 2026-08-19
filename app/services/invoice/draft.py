from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.document_engine.rendering.context import Values


@dataclass(slots=True, frozen=True)
class PartySelection:
    organization_id: int
    tax_id_id: int
    representative_id: int | None = None
    bank_account_id: int | None = None


@dataclass(slots=True, frozen=True)
class LineInput:
    """One typed incoice line. Descriptions are keyed by language code."""

    descriptions: Values
    unit_code: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal


@dataclass(slots=True, frozen=True)
class InvoiceDraft:
    template_id: int
    sequence_id: int
    currency_code: str
    issue_date: date
    provider: PartySelection
    client: PartySelection
    lines: tuple[LineInput, ...]