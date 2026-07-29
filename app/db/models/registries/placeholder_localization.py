from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.references.language import Language

if TYPE_CHECKING:
    from app.db.models.registries.placeholder import PlaceholderRegistry


class PlaceholderRegistryLocalization(Base):
    __tablename__ = "placeholder_registry_localizations"

    placeholder_key: Mapped[str] = mapped_column(
        ForeignKey("placeholder_registry.key"),
        primary_key=True,
    )

    language_code: Mapped[str] = mapped_column(
        ForeignKey("languages.code"),
        primary_key=True,
    )

    placeholder: Mapped[PlaceholderRegistry] = relationship(
        foreign_keys=[placeholder_key],
        back_populates="localizations",
    )

    language: Mapped[Language] = relationship(
        foreign_keys=[language_code],
    )

    label: Mapped[str | None] = mapped_column(
        String(60),
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
    )