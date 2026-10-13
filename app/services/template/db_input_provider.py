from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.configs.default_template_config import DefaultTemplateConfig
from app.db.models.registries.placeholder import PlaceholderRegistry
from app.document_engine.blueprint.models.template import TemplateConfig
from app.services.errors import EntityNotFound
from app.core.messages import QT_TRANSLATE_NOOP


class DbTemplateInputProvider:
    """Production TemplateInputProvider, reads seeded reference data."""

    def __init__(
            self,
            session: Session,
            config: TemplateConfig | None = None,
    ) -> None:
        
        self._session = session
        self._config = config


    def default_template_config(self) -> TemplateConfig:

        if self._config is None:
            row = self._session.scalars(select(DefaultTemplateConfig)).first()
            if row is None:
                raise EntityNotFound(
                    "no default template config configured",
                    user_message=QT_TRANSLATE_NOOP("messages", "Application defaults are missing."),
                )
            
            self._config = TemplateConfig(
                primary_language=row.primary_language_code,
                secondary_language=row.secondary_language_code,
                type=row.document_type_code,
                name=row.name,
                description=row.description,
                append_currency=row.append_currency,
            )

        return self._config
    

    def placeholder_defaults(self) -> dict[str, dict[str, Any]]:

        return {
            ph.key: {
                "active": ph.active,
                "required": ph.required,
                "type": ph.type,
            }
            for ph in self._session.scalars(select(PlaceholderRegistry))
        }
    

    def languages(self) -> set[str]:

        config = self.default_template_config()
        return { c for c in (config.primary_language, config.secondary_language) if c }