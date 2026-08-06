from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship, attribute_keyed_dict

from app.db.base import Base
from app.db.models.core.organization_localization import OrganizationLocalization
from app.db.associations import organization_representative_m2m

if TYPE_CHECKING:
    from app.db.models.core.representative import Representative
    from app.db.models.core.bank_account import BankAccount
    from app.db.models.core.tax_id import TaxId
    from app.db.models.core.document_sequence import DocumentSequence


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str | None] = mapped_column(
        String(255),
    )

    phone: Mapped[str | None] = mapped_column(
        String(16),
    )

    localizations: Mapped[dict[str, OrganizationLocalization]] = relationship(
        back_populates="organization",
        collection_class=attribute_keyed_dict("language_code"),
        cascade="all, delete-orphan",
    )

    representatives: Mapped[list[Representative]] = relationship(
        secondary=organization_representative_m2m,
        back_populates="organizations",
    )

    bank_accounts: Mapped[list[BankAccount]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    tax_ids: Mapped[list[TaxId]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    sequences: Mapped[list[DocumentSequence]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )