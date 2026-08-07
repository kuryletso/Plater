from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.registries.document_type import DocumentTypeRegistry

if TYPE_CHECKING:
    from app.db.models.core.organization import Organization


class DocumentSequence(Base):
    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "document_type_code",
            "prefix",
            name="unique_organization_id_document_type_prefix"
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    document_type_code: Mapped[str] = mapped_column(
        ForeignKey("document_type_registry.code"),
    )

    document_type: Mapped[DocumentTypeRegistry] = relationship()

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
    )

    organization: Mapped[Organization] = relationship(
        foreign_keys=[organization_id],
        back_populates="sequences",
    )

    prefix: Mapped[str | None] = mapped_column(
        String(32),
    )

    counter: Mapped[int]

    padding: Mapped[int]