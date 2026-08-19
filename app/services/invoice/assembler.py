from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.organization import Organization
from app.db.models.core.representative import Representative as RepresentativeORM
from app.db.models.core.tax_id import TaxId as TaxIdORM
from app.db.models.core.bank_account import BankAccount as BankAccountORM
from app.db.models.core.invoice_line import InvoiceLine
from app.db.models.references.country import Country
from app.db.models.references.currency import Currency
from app.db.models.references.language import Language
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.db.models.registries.placeholder import PlaceholderRegistry
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry

from app.document_engine.blueprint.models.template import TemplateConfig
from app.document_engine.rendering.context import Values

from app.services.errors import EntityNotFound, InvalidSelection
from app.services.language import LanguageSpec
from app.services.money import MoneyFormat
from app.services.invoice.data import (
    InvoiceData, Party, Line, Representative, TaxId, BankDetails,
)
from app.services.invoice.draft import InvoiceDraft, PartySelection, LineInput
from app.services.doc_sequence.repository import IssuedNumber


def values_of(
        localizations: Mapping[str, Any],
        attr: str,
        codes: tuple[str, ...],
) -> Values:
    """Pull one localized attribute into a {language: value} mapping."""

    out: dict[str, str] = {}
    for code in codes:
        loc = localizations.get(code)
        if loc is None:
            continue
        value = getattr(loc, attr)
        if value is not None:
            out[code] = value
    
    return out


def resolve_languages(
        session: Session,
        config: TemplateConfig,
) -> tuple[LanguageSpec, ...]:
    
    codes = tuple(
        c for c
        in (config.primary_language, config.secondary_language)
        if c
    )
    rows = {
        lang.code: lang
        for lang in session.scalars(
            select(Language).where(Language.code.in_(codes))
        )
    }

    missing = [ c for c in codes if c not in rows ]
    if missing:
        raise EntityNotFound(
            f"languages not found: {missing}",
            context={"codes": missing},
        )
    
    return tuple(
        LanguageSpec(code=c, alpha_2=rows[c].code_alpha_2)
        for c in codes
    )


def build_labels(
        session: Session,
        codes: tuple[str, ...],
) -> dict[str, Values]:
    
    labels: dict[str, Values] = {}
    for ph in session.scalars(
        select(PlaceholderRegistry).options(
            selectinload(PlaceholderRegistry.localizations),
        )
    ):
        
        localized = values_of(ph.localizations, "label", codes)
        if localized:
            labels[ph.key] = localized

    return labels


def money_format(
        currency: Currency,
        codes: tuple[str, ...],
) -> MoneyFormat:
    
    return MoneyFormat(
        code=currency.code,
        decimal_places=currency.decimal_places,
        decimal_separator=currency.decimal_separator,
        grouping_separator=currency.grouping_separator,
        symbol_position=currency.symbol_position,
        symbol_spacing=currency.symbol_spacing,
        symbols=values_of(currency.localizations, "symbol", codes),
    )


class InvoiceAssembler:

    def __init__(
            self,
            session: Session,
            languages: tuple[LanguageSpec, ...],
    ) -> None:
        
        self._session = session
        self._langs = languages
        self._codes = tuple(lang.code for lang in languages)


    def assemble(
            self,
            draft: InvoiceDraft,
            number: IssuedNumber,
    ) -> InvoiceData:
        
        currency = self._get(Currency, draft.currency_code, "currency")

        return InvoiceData(
            prefix=number.prefix or "",
            number=number.number,
            issue_date=draft.issue_date,
            currency=money_format(currency, self._codes),
            provider=self._party(draft.provider),
            client=self._party(draft.client),
            lines=self._lines(draft.lines),
        )
    

    def _get(
            self,
            model,
            pk,
            label: str,
    ):
        entity = self._session.get(model, pk)
        if entity is None:
            raise EntityNotFound(
                f"{label} {pk!r} not found",
                context={"model": model.__name__, "pk": pk},
            )
        
        return entity
    

    def _party(
            self,
            selection: PartySelection,
    ) -> Party:
        
        org = self._session.scalar(
            select(Organization)
            .where(Organization.id == selection.organization_id)
            .options(
                selectinload(Organization.localizations),
                selectinload(Organization.tax_ids)
                    .selectinload(TaxIdORM.tax_id_system)
                    .selectinload(TaxIdSystemRegistry.localizations),
                selectinload(Organization.tax_ids)
                    .selectinload(TaxIdORM.country)
                    .selectinload(Country.localizations),
                selectinload(Organization.representatives)
                    .selectinload(RepresentativeORM.localizations),
                selectinload(Organization.bank_accounts)
                    .selectinload(BankAccountORM.localizations),
            )
        )

        if org is None:
            raise EntityNotFound(
                f"Organization {selection.organization_id} not found.",
                context={"organization_id": selection.organization_id},
            )
        
        return Party(
            legal_name=values_of(org.localizations, "legal_name", self._codes),
            address=values_of(org.localizations, "address", self._codes),
            org_type=values_of(org.localizations, "org_type", self._codes),
            tax_id=self._tax_id(org, selection.tax_id_id),
            email=org.email,
            phone=org.phone,
            representative=self._representative(org, selection.representative_id),
            bank=self._bank(org, selection.bank_account_id),
        )
    

    def _tax_id(
            self,
            org: Organization,
            tax_id_id: int,
    ) -> TaxId:
        
        match = next( ( t for t in org.tax_ids if t.id == tax_id_id ), None )
        if match is None:
            raise InvalidSelection(
                f"organization {org.id} has no tax id {tax_id_id}",
                user_message="Select a tax ID for this organization.",
                context={"organization_id": org.id, "tax_id_id": tax_id_id},
            )
        
        return TaxId(
            value=match.value,
            system=values_of(match.tax_id_system.localizations, "name", self._codes),
            country=values_of(match.country.localizations, "name", self._codes),
        )
    

    def _representative(
            self,
            org: Organization,
            representative_id: int | None,
    ) -> Representative | None:
        
        if representative_id is None:
            return None
        
        match = next(
            ( r for r in org.representatives if r.id == representative_id ),
            None,
        )

        if match is None:
            raise InvalidSelection(
                f"Organization {org.id} has no representative {representative_id}",
                user_message="The selected representative is not linked to this organization.",
                context={"organization_id": org.id, "representative_id": representative_id},
            )
        
        return Representative(
            name=values_of(match.localizations, "name", self._codes),
            title=values_of(match.localizations, "title", self._codes) or None,
        )
    

    def _bank(
            self,
            org: Organization,
            bank_account_id: int | None,
    ) -> BankDetails | None:
        
        if bank_account_id is None:
            return None
        
        match = next(
            ( b for b in org.bank_accounts if b.id == bank_account_id ),
            None,
        )

        if match is None:
            raise InvalidSelection(
                f"Organization {org.id} has no bank account {bank_account_id}",
                user_message="The selected bank account is not linked to this organization.",
                context={"organization_id": org.id, "bank_account_id": bank_account_id},
            )
        

        return BankDetails(
            iban=match.iban,
            swift=match.swift,
            bank_name=values_of(match.localizations, "bank_name", self._codes),
            bank_info=values_of(match.localizations, "bank_info", self._codes),
        )
    

    def _lines(
            self,
            lines: tuple[LineInput, ...],
    ) -> tuple[Line, ...]:

        units: dict[str, MeasurementUnitRegistry] = {}
        for line in lines:
            if line.unit_code in units:
                continue

            unit = self._session.get(MeasurementUnitRegistry, line.unit_code)
            if unit is None:
                raise EntityNotFound(
                    f"measurement unit {line.unit_code!r} not found",
                    context={"code": line.unit_code},
                )
            units[line.unit_code] = unit

        return tuple(
            Line(
                description={
                    code: text
                    for code, text in line.descriptions.items()
                    if code in self._codes and text
                },
                unit=values_of(units[line.unit_code].localizations, "name", self._codes),
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
            )
            for line in lines
        )