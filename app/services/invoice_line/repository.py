from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.invoice_line import InvoiceLine
from app.db.models.core.invoice_line_localization import InvoiceLineLocalization, description_key
from app.db.models.references.language import Language
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.sentinel import UNSET, Unset
from app.core.messages import QT_TRANSLATE_NOOP


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
        self._check_descriptions_free(localizations)

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
                    .where(InvoiceLineLocalization.description.icontains(search, autoescape=True)),
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
            self._check_descriptions_free(localizations, line_id)
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
            primary: str | None = None,
    ) -> InvoiceLine:
        """Cache write-back after a successful generate, one saved line per description.

        The line holding primary language description takes the latest values, or a new line is created. 
        Every description given then belongs to that line, taken from whichever line had it before. 
        Languages that are not used keep their text. Line left with no description is deleted. 
        `primary` defaults to the first language given.
        """

        self._check_localizations(localizations)
        self._check_measurement_unit(measurement_unit)
        self._check_amounts(quantity, unit_price, tax_rate)

        lookup = primary if primary is not None and primary in localizations else next(iter(localizations))
        owner = self._owner(lookup, localizations[lookup].description)

        if owner is None:
            line = InvoiceLine(use_count=0)
            self._session.add(line)
        else:
            line = owner.invoice_line

        line.quantity = quantity
        line.measurement_unit_code = measurement_unit
        line.unit_price = unit_price
        line.tax_rate = tax_rate
        line.use_count += 1
        line.last_used_at = datetime.now(UTC)

        # Frees the description first and flushes, then writes new row. Single flush would write rows 
        # before it deletes them, which the unqique constraint would refuse otherwise.

        for code, text in localizations.items():
            taken = self._owner(code, text.description)
            if taken is not None and taken.invoice_line is not line:
                donor = taken.invoice_line
                del donor.localizations[code]
                if not donor.localizations:
                    self._session.delete(donor)
        self._session.flush()

        for code, text in localizations.items():
            row = line.localizations.get(code)
            if row is None:
                line.localizations[code] = InvoiceLineLocalization(
                    language_code=code,
                    description=text.description,
                )
            else:
                row.description = text.description

        self._session.commit()

        return line


    def hints(
            self,
            language: str,
            search: str | None = None,
            *,
            limit: int = 20,
    ) -> list[InvoiceLine]:
        """Autocomplete candidates, lines which `language` description contains 
        `search`, best first. Filtering and scoring happen in Python:
        the cache is small, casefild() handles Cyrillic, uses frecency formula.
        """

        now = datetime.now(UTC)
        needle = search.casefold() if search else None

        def matches(line: InvoiceLine) -> bool:
            row = line.localizations.get(language)
            if row is None:
                return False
            return needle is None or needle in row.description.casefold()

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
                user_message=QT_TRANSLATE_NOOP("messages", "Enter the line description in at least one language."),
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
                user_message=QT_TRANSLATE_NOOP("messages", "Selected measurement unit is no longer available."),
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
                user_message=QT_TRANSLATE_NOOP("messages", "Quantity must be greater than zero."),
                context={"quantity": quantity},
            )

        if unit_price < 0:
            raise InvalidSelection(
                f"unit price cannot be negative, got {unit_price}",
                user_message=QT_TRANSLATE_NOOP("messages", "Unit price cannot be negative."),
                context={"unit_price": unit_price},
            )

        if tax_rate < 0:
            raise InvalidSelection(
                f"tax rate cannot be negative, got {tax_rate}",
                user_message=QT_TRANSLATE_NOOP("messages", "Tax rate cannot be negative."),
                context={"tax_rate": tax_rate},
            )


    def _check_descriptions_free(
            self,
            localizations: Mapping[str, InvoiceLineText],
            line_id: int | None = None,
    ) -> None:
        """Descrption belongs to one saved line per language."""

        for code, text in localizations.items():
            owner = self._owner(code, text.description)
            if owner is not None and owner.invoice_line_id != line_id:
                raise InvalidSelection(
                    f"line {owner.invoice_line_id} already has this {code} description",
                    user_message=QT_TRANSLATE_NOOP("messages", "Another saved invoice line already has this description."),
                    context={"line_id": owner.invoice_line_id, "language": code},
                )


    def _owner(self, language: str, description: str) -> InvoiceLineLocalization | None:
        return self._session.scalar(
            select(InvoiceLineLocalization)
                .where(
                    InvoiceLineLocalization.language_code == language,
                    InvoiceLineLocalization.description_key == description_key(description),
                )
        )