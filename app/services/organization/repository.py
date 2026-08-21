from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.bank_account import BankAccount
from app.db.models.core.bank_account_localization import BankAccountLocalization
from app.db.models.core.document_sequence import DocumentSequence
from app.db.models.core.organization import Organization
from app.db.models.core.organization_localization import OrganizationLocalization
from app.db.models.core.representative import Representative
from app.db.models.core.tax_id import TaxId
from app.db.models.references.country import Country
from app.db.models.references.currency import Currency
from app.db.models.references.language import Language
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry
from app.services.sentinel import Unset, UNSET
from app.services.errors import EntityNotFound, InvalidSelection


@dataclass(slots=True, frozen=True)
class OrganizationText:
    """One language's worth of an organization's identity."""

    org_type: str
    legal_name: str
    address: str | None = None


@dataclass(slots=True, frozen=True)
class BankText:
    bank_name: str | None = None
    bank_info: str | None = None


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session


    def create(
            self,
            localizations: Mapping[str, OrganizationText],
            *,
            email: str | None = None,
            phone: str | None = None,
    ) -> Organization:

        self._check_localizations(localizations)

        organization = Organization(
            email=email,
            phone=phone,
            localizations={
                code: OrganizationLocalization(
                    language_code=code,
                    org_type=text.org_type,
                    legal_name=text.legal_name,
                    address=text.address,
                )
                for code, text in localizations.items()
            },
        )

        self._session.add(organization)
        self._session.commit()

        return organization


    def get(self, organization_id: int) -> Organization:
        organization = self._session.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .options(
                selectinload(Organization.localizations),
                selectinload(Organization.tax_ids),
                selectinload(Organization.bank_accounts)
                    .selectinload(BankAccount.localizations),
                selectinload(Organization.representatives)
                    .selectinload(Representative.localizations),
            )
        )

        if organization is None:
            raise EntityNotFound(
                f"organization {organization_id} not found",
                context={"organization_id": organization_id},
            )
        
        return organization


    def list(
            self,
            *,
            search: str | None = None,
    ) -> list[Organization]:
        """Every organization, newest first; 'search' matches any localized name."""

        query = (
            select(Organization)
            .options(
                selectinload(Organization.localizations),
                selectinload(Organization.tax_ids)
                    .selectinload(TaxId.tax_id_system)
                        .selectinload(TaxIdSystemRegistry.localizations),
            ).order_by(Organization.id.desc())
        )

        if search:
            query = query.where(
                Organization.id.in_(
                    select(OrganizationLocalization.organization_id)
                    .where(OrganizationLocalization.legal_name.icontains(search)),
                )
            )

        return list(self._session.scalars(query).unique().all())


    def update(
            self,
            organization_id: int,
            *,
            email: str | None | Unset = UNSET,
            phone: str | None | Unset = UNSET,
            localizations: Mapping[str, OrganizationText] | Unset = UNSET,
    ) -> Organization:

        organization = self.get(organization_id)

        if not isinstance(localizations, Unset):
            self._check_localizations(localizations)

        if not isinstance(email, Unset):
            organization.email = email

        if not isinstance(phone, Unset):
            organization.phone = phone

        if not isinstance(localizations, Unset):
            current = organization.localizations

            for code, value in localizations.items():
                row = current.get(code)

                if row is None:
                    current[code] = OrganizationLocalization(
                        language_code=code,
                        org_type=value.org_type,
                        legal_name=value.legal_name,
                        address=value.address,
                    )

                else:
                    row.org_type = value.org_type
                    row.legal_name = value.legal_name
                    row.address = value.address

            for code in set(current) - set(localizations):
                del current[code]

        self._session.commit()

        return organization


    def delete(self, organizaiton_id: int) -> None:
        """Refused once the organization has issued invoice numbers."""

        organization = self.get(organizaiton_id)

        self._session.delete(organization)
        self._session.commit()


    def add_tax_id(
            self,
            organization_id: int,
            *,
            tax_id_system: str,
            country: str,
            value: str,
    ) -> TaxId:

        organization = self.get(organization_id)
        self._check_tax_id_system(tax_id_system)
        self._check_country(country)

        duplicate = any(
            t.tax_id_system_code == tax_id_system and t.country_code == country
            for t in organization.tax_ids
        )
        if duplicate:
            raise InvalidSelection(
                f"organization {organization_id} already has a {tax_id_system} "
                f"identifier for {country}",
                user_message="That tax identifier is already recorded.",
                context={"tax_id_system": tax_id_system, "country": country},
            )

        tax_id = TaxId(
            organization_id=organization_id,
            tax_id_system_code=tax_id_system,
            country_code=country,
            value=value,
        )

        self._session.add(tax_id)
        self._session.commit()

        return tax_id


    def remove_tax_id(
            self,
            organization_id: int,
            tax_id_id: int,
    ) -> None:

        organization = self.get(organization_id)

        tax_id = next(
            ( t for t in organization.tax_ids if t.id == tax_id_id ),
            None,
        )
        if tax_id is None:
            raise InvalidSelection(
                f"organization {organization_id} has no tax id {tax_id_id}",
                context={"organization_id": organization_id, "tax_id_id": tax_id_id},
            )

        organization.tax_ids.remove(tax_id)
        self._session.commit()


    def add_bank_account(
            self,
            organization_id: int,
            *,
            iban: str,
            currency: str,
            country: str,
            swift: str | None = None,
            localizations: Mapping[str, BankText] | None = None,
    ) -> BankAccount:

        self.get(organization_id)
        self._check_currency(currency)
        self._check_country(country)

        existing = self._session.scalar(
            select(BankAccount).where(BankAccount.iban == iban)
        )
        if existing is not None:
            raise InvalidSelection(
                f"IBAN {iban} is already recorded",
                user_message="Provided IBAN is already used by another account.",
                context={"iban": iban},
            )

        account = BankAccount(
            organization_id=organization_id,
            iban=iban,
            swift=swift,
            currency_code=currency,
            country_code=country,
            localizations={
                code: BankAccountLocalization(
                    language_code=code,
                    bank_name=text.bank_name,
                    bank_info=text.bank_info,
                )
                for code, text in (localizations or {}).items()
            },
        )

        self._session.add(account)
        self._session.commit()

        return account


    def remove_bank_account(
            self,
            organization_id: int,
            bank_account_id: int,
    ) -> None:

        organization = self.get(organization_id)

        account = next(
            ( b for b in organization.bank_accounts if b.id == bank_account_id ),
            None,
        )

        if account is None:
            raise InvalidSelection(
                f"organization {organization_id} has no bank account {bank_account_id}",
                context={
                    "organization_id": organization_id,
                    "bank_account_id": bank_account_id,
                },
            )

        organization.bank_accounts.remove(account)
        self._session.commit()


    def attach_representative(
            self,
            organization_id: int,
            representative_id: int,
    ) -> None:
        organization = self.get(organization_id)
        representative = self._session.get(Representative, representative_id)

        if representative is None:
            raise EntityNotFound(
                f"representative {representative_id} not found",
                context={"representative_id": representative_id},
            )

        if representative not in organization.representatives:
            organization.representatives.append(representative)
            self._session.commit()


    def detach_representative(
            self,
            organization_id: int,
            representative_id: int,
    ) -> None:

        organization = self.get(organization_id)

        representative = next(
            ( r for r in organization.representatives if r.id == representative_id),
            None,
        )
        if representative is None:
            raise InvalidSelection(
                f"organization {organization_id} has no representative {representative_id}",
                context={
                    "organization_id": organization_id,
                    "representative_id": representative_id,
                },
            )

        organization.representatives.remove(representative)
        self._session.commit()


    def _check_localizations(
            self,
            localizations: Mapping[str, OrganizationText],
    ) -> None:
        if not localizations:
            raise InvalidSelection(
                "organization needs at least one localization",
                user_message="Enter the organization name in at least one language.",
            )

        for code in localizations:
            if self._session.get(Language, code) is None:
                raise EntityNotFound(
                    f"language {code!r} not found",
                    context={"code": code},
                )


    def _check_country(self, code: str) -> None:
        if self._session.get(Country, code) is None:
            raise EntityNotFound(f"country {code!r} not found", context={"code": code})


    def _check_currency(self, code: str) -> None:
        if self._session.get(Currency, code) is None:
            raise EntityNotFound(f"currency {code!r} not found", context={"code": code})


    def _check_tax_id_system(self, code: str) -> None:
        row = self._session.get(TaxIdSystemRegistry, code)

        if row is None:
            raise EntityNotFound(
                f"tax id system {code!r} not found",
                context={"code": code},
            )

        if not row.active:
            raise InvalidSelection(
                f"tax id system {code!r} is disabled",
                user_message="Selected tax system is no longer available.",
                context={"code": code},
            )