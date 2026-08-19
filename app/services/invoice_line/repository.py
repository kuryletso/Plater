from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.invoice_line import InvoiceLine
from app.db.models.core.invoice_line_localization import InvoiceLineLocalization
from app.db.models.references.language import Language
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.sentinel import UNSET, Unset


@dataclass(slots=True, frozen=True)
class InvoiceLineText:
    """One language's worth of an invoice line's description."""

    description: str


class InvoiceLineRepository:
    """Catalog of reusable invoice lines. Drafts reference them by id."""

    def __init__(self, session: Session) -> None:
        self._session = session


    def create(
            self,
            localizations: Mapping[str, InvoiceLineText],
            *,
            quantity: Decimal,
            measurement_unit: str,
            unit_price: Decimal,
            tax_rate: Decimal,
    ) -> InvoiceLine:

        self._check_localizations(localizations)
        self._check_measurement_unit(measurement_unit)
        self._check_amounts(quantity, unit_price, tax_rate)

        line = InvoiceLine(
            quantity=quantity,
            measurement_unit_code=measurement_unit,
            unit_price=unit_price,
            tax_rate=tax_rate,
            localizations={
                code: InvoiceLineLocalization(
                    language_code=code,
                    description=text.description,
                )
                for code, text in localizations.items()
            },
        )

        self._session.add(line)
        self._session.commit()

        return line


    def get(self, line_id: int) -> InvoiceLine:
        line = self._session.scalar(
            select(InvoiceLine)
            .where(InvoiceLine.id == line_id)
            .options(
                selectinload(InvoiceLine.localizations),
                selectinload(InvoiceLine.measurement_unit),
            )
        )

        if line is None:
            raise EntityNotFound(
                f"invoice line {line_id} not found",
                context={"line_id": line_id},
            )

        return line


    def list(
            self,
            *,
            search: str | None = None,
    ) -> list[InvoiceLine]:
        """Newest first; 'search' matches any localized description."""

        query = (
            select(InvoiceLine)
            .options(selectinload(InvoiceLine.localizations))
            .order_by(InvoiceLine.id.desc())
        )

        if search:
            query = query.where(
                InvoiceLine.id.in_(
                    select(InvoiceLineLocalization.invoice_line_id)
                    .where(InvoiceLineLocalization.description.icontains(search)),
                )
            )

        return list(self._session.scalars(query).unique().all())


    def update(
            self,
            line_id: int,
            *,
            quantity: Decimal | Unset = UNSET,
            measurement_unit: str | Unset = UNSET,
            unit_price: Decimal | Unset = UNSET,
            tax_rate: Decimal | Unset = UNSET,
            localizations: Mapping[str, InvoiceLineText] | Unset = UNSET,
    ) -> InvoiceLine:

        line = self.get(line_id)

        if not isinstance(localizations, Unset):
            self._check_localizations(localizations)
        if not isinstance(measurement_unit, Unset):
            self._check_measurement_unit(measurement_unit)

        self._check_amounts(
            line.quantity if isinstance(quantity, Unset) else quantity,
            line.unit_price if isinstance(unit_price, Unset) else unit_price,
            line.tax_rate if isinstance(tax_rate, Unset) else tax_rate,
        )

        if not isinstance(quantity, Unset):
            line.quantity = quantity
        if not isinstance(measurement_unit, Unset):
            line.measurement_unit_code = measurement_unit
        if not isinstance(unit_price, Unset):
            line.unit_price = unit_price
        if not isinstance(tax_rate, Unset):
            line.tax_rate = tax_rate

        if not isinstance(localizations, Unset):
            current = line.localizations

            for code, text in localizations.items():
                row = current.get(code)

                if row is None:
                    current[code] = InvoiceLineLocalization(
                        language_code=code,
                        description=text.description,
                    )
                else:
                    row.description = text.description

            for code in set(current) - set(localizations):
                del current[code]

        self._session.commit()

        return line


    def delete(self, line_id: int) -> None:
        """Permissive: nothing stores invoices, so no line is ever 'in use'."""

        line = self.get(line_id)

        self._session.delete(line)
        self._session.commit()


    def touch(
            self,
            localizations: Mapping[str, InvoiceLineText],
            *,
            quantity: Decimal,
            measurement_unit: str,
            unit_price: Decimal,
            tax_rate: Decimal,
    ) -> InvoiceLine:
        """Cache write-back after a successful generate. Bump the match or store a new hint.
        Quantity is per-invoice, so it never participates in matching
        and only remembered a 'last used'.
        """

        typed = {
            code: text.description.casefold()
            for code, text in localizations.items()
        }

        for line in self.list():
            if line.measurement_unit_code != measurement_unit:
                continue
            if line.unit_price != unit_price or line.tax_rate != tax_rate:
                continue

            stored = {
                code: row.description.casefold()
                for code, row in line.localizations.items()
            }
            if stored != typed:
                continue

            line.use_count += 1
            line.last_used_at = datetime.now(UTC)
            line.quantity = quantity
            self._session.commit()
            return line

        return self.create(
            localizations=localizations,
            quantity=quantity,
            measurement_unit=measurement_unit,
            unit_price=unit_price,
            tax_rate=tax_rate,
        )


    def hints(
            self,
            search: str | None = None,
            *,
            limit: int = 20,
    ) -> list[InvoiceLine]:
        """Autocomplete candidates, best first. Filtering and scoring happen in Python:
        the cache is small, casefild() handles Cyrillic, uses frecency formula."""

        now = datetime.now(UTC)
        needle = search.casefold() if search else None

        def matches(line: InvoiceLine) -> bool:
            if needle is None:
                return True
            return any(
                needle in row.description.casefold()
                for row in line.localizations.values()
            )

        def score(line: InvoiceLine) -> float:
            last_used = line.last_used_at
            if last_used.tzinfo is None:        # (!) SQLite returs datetime without timezone
                last_used = last_used.replace(tzinfo=UTC)
            age_days = max((now - last_used).total_seconds() / 86400, 0.0)
            return line.use_count * 2 ** (-age_days / 30)

        candidates = [ line for line in self.list() if matches(line) ]
        candidates.sort(key=score, reverse=True)

        return candidates[:limit]


    def _check_localizations(
            self,
            localizations: Mapping[str, InvoiceLineText],
    ) -> None:

        if not localizations:
            raise InvalidSelection(
                "invoice line needs at least one localization",
                user_message="Enter the line description in at least one language.",
            )

        for code in localizations:
            if self._session.get(Language, code) is None:
                raise EntityNotFound(
                    f"language {code!r} not found",
                    context={"code": code},
                )


    def _check_measurement_unit(self, code: str) -> None:
        row = self._session.get(MeasurementUnitRegistry, code)

        if row is None:
            raise EntityNotFound(
                f"measurement unit {code!r} not found",
                context={"code": code},
            )

        if not row.active:
            raise InvalidSelection(
                f"measurement unit {code!r} is disabled",
                user_message="Selected measurement unit is no longer available.",
                context={"code": code},
            )


    def _check_amounts(
            self,
            quantity: Decimal,
            unit_price: Decimal,
            tax_rate: Decimal,
    ) -> None:

        if quantity <= 0:
            raise InvalidSelection(
                f"quantity must be positive, got {quantity}",
                user_message="Quantity must be greater than zero.",
                context={"quantity": quantity},
            )

        if unit_price < 0:
            raise InvalidSelection(
                f"unit price cannot be negative, got {unit_price}",
                user_message="Unit price cannot be negative.",
                context={"unit_price": unit_price},
            )

        if tax_rate < 0:
            raise InvalidSelection(
                f"tax rate cannot be negative, got {tax_rate}",
                user_message="Tax rate cannot be negative",
                context={"tax_rate": tax_rate},
            )