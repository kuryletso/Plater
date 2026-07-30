from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime, UTC

from sqlalchemy import ForeignKey, DateTime, UniqueConstraint, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.core.template import Template


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "version",
            name="unique_template_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))

    version: Mapped[int]

    source_sha256: Mapped[str] = mapped_column(String(64))      # hash of the source .docx

    sections: Mapped[list] = mapped_column(JSON)

    placeholders: Mapped[dict] = mapped_column(JSON)

    config: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    template: Mapped[Template] = relationship(back_populates="versions")