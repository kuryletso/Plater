from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.references.language import Language
from app.db.models.registries.document_type import DocumentTypeRegistry


class DefaultTemplateConfig(Base):
    __tablename__ = "default_template_config"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    primary_language_code: Mapped[str] = mapped_column(
        ForeignKey("languages.code"),
    )

    primary_language: Mapped[Language] = relationship(
        foreign_keys=[primary_language_code],
    )

    secondary_language_code: Mapped[str | None] = mapped_column(
        ForeignKey("languages.code"),
    )

    secondary_language: Mapped[Language | None] = relationship(
        foreign_keys=[secondary_language_code],
    )

    document_type_code: Mapped[str] = mapped_column(
        ForeignKey("document_type_registry.code"),
    )

    document_type: Mapped[DocumentTypeRegistry] = relationship()

    name: Mapped[str] = mapped_column(
        String(255),
    )

    description: Mapped[str] = mapped_column(
        String(255),
    )

    append_currency: Mapped[bool] = mapped_column(
        default=False,
    )

    date_format: Mapped[str] = mapped_column(
        String(20),
        default="y-MM-dd",
        server_default="y-MM-dd",
    )