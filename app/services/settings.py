from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.configs.default_template_config import DefaultTemplateConfig
from app.db.models.references.language import Language
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.services.sentinel import Unset, UNSET
from app.services.errors import EntityNotFound, InvalidSelection


class TemplateDefaultService:
    """The single row of pre-fill values used when importing a new template."""

    DEFAULT_PRIMARY_LANGUAGE = "ENG"
    DEFAULT_SECONDARY_LANGUAGE = "UKR"
    DEFAULT_DOCUMENT_TYPE = "invoice"

    def __init__(self, session: Session) -> None:
        self._session = session


    def ensure(self) -> DefaultTemplateConfig:
        """Create the row if this is a fresh database. Called once from init_db()."""

        existing = self._session.scalars(select(DefaultTemplateConfig)).first()
        if existing is not None:
            return existing

        row = DefaultTemplateConfig(
            primary_language_code=self.DEFAULT_PRIMARY_LANGUAGE,
            secondary_language_code=self.DEFAULT_SECONDARY_LANGUAGE,
            document_type_code=self.DEFAULT_DOCUMENT_TYPE,
            name="Invoice",
            description="",
            append_currency=True,
        )
        self._session.add(row)
        self._session.commit()

        return row


    def get(self) -> DefaultTemplateConfig:
        row = self._session.scalars(select(DefaultTemplateConfig)).first()

        if row is None:
            raise EntityNotFound(
                "template defaults have not been initialised",
                user_message="Application defaults are missing",
            )

        return row


    def update(
            self,
            *,
            primary_language: str | Unset = UNSET,
            secondary_language: str | None | Unset = UNSET,
            document_type: str | Unset = UNSET,
            name: str | Unset = UNSET,
            description: str | Unset = UNSET,
            append_currency: bool | Unset = UNSET,
    ) -> DefaultTemplateConfig:

        row = self.get()

        new_primary = self._language(primary_language) \
            if not isinstance(primary_language, Unset) \
            else row.primary_language_code

        if isinstance(secondary_language, Unset):
            new_secondary = row.secondary_language_code
        elif secondary_language is None:
            new_secondary = None
        else:
            new_secondary = self._language(secondary_language)

        if new_secondary is not None and new_secondary == new_primary:
            raise InvalidSelection(
                "the secondary language must differ from the primary one",
                user_message="Select different secondary language.",
                context={"language": row.primary_language_code},
            )

        new_type = self._document_type(document_type) \
            if not isinstance(document_type, Unset) \
            else row.document_type_code

        row.primary_language_code = new_primary
        row.secondary_language_code = new_secondary
        row.document_type_code = new_type

        for field, value in (
            ("name", name),
            ("description", description),
            ("append_currency", append_currency),
        ):
            if not isinstance(value, Unset):
                setattr(row, field, value)

        self._session.commit()

        return row


    def _language(self, code: str) -> str:
        if self._session.get(Language, code) is None:
            raise EntityNotFound(
                f"language {code!r} not found",
                context={"code": code},
            )
        return code


    def _document_type(self, code: str) -> str:
        row = self._session.get(DocumentTypeRegistry, code)

        if row is None:
            raise EntityNotFound(
                f"document type {code!r} not found",
                context={"code": code},
            )
        if not row.active:
            raise InvalidSelection(
                f"document_type {code!r} is disabled",
                user_message="Selected document type is not longer available.",
                context={"code": code},
            )

        return code