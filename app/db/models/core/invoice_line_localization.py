from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.db.models.references.language import Language

if TYPE_CHECKING:
    from app.db.models.core.invoice_line import InvoiceLine


def description_key(description: str) -> str:
    """Simplified description used for unique constraint, stripped of case and spacing."""

    return " ".join(description.split()).casefold()


class InvoiceLineLocalization(Base):
    __tablename__ = "invoice_line_localizations"

    __table_args__ = (
        UniqueConstraint("language_code", "description_key"),
    )

    invoice_line_id: Mapped[int] = mapped_column(
        ForeignKey("invoice_lines.id"),
        primary_key=True,
    )

    language_code: Mapped[str] = mapped_column(
        ForeignKey("languages.code"),
        primary_key=True,
    )

    invoice_line: Mapped[InvoiceLine] = relationship(
        foreign_keys=[invoice_line_id],
        back_populates="localizations",
    )

    language: Mapped[Language] = relationship(
        foreign_keys=[language_code],
    )

    description: Mapped[str] = mapped_column(
        String(255),
    )

    description_key: Mapped[str] = mapped_column(String(255))

    @validates("description")
    def _keep_key(self, _attribute: str, description: str) -> str:
        self.description_key = description_key(description)
        return description