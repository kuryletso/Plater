from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime, UTC

from sqlalchemy import JSON, String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.core.template_version import TemplateVersion

class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str | None] = mapped_column(       # Set for shipped default templates, NULL for user uploads
        String(60),
        unique=True,
    )

    name: Mapped[str] = mapped_column(String(255))

    type: Mapped[str] = mapped_column(String(30))       # document_type code

    system: Mapped[bool] = mapped_column(default=False, server_default=text("0"))

    active: Mapped[bool] = mapped_column(default=True, server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    versions: Mapped[list[TemplateVersion]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateVersion.version",
    )
