from dataclasses import dataclass

from typing import cast

from sqlalchemy.orm import Session

from enum import StrEnum

from app.document_engine.version import ENGINE_VERSION

from app.core.errors import AppError
from app.core.diagnostics import DiagnosticCollector
from app.services.template.repository import TemplateRepository
from app.services.template.import_service import TemplateImportService
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.errors import BlueprintUnreadable
from app.db.models.core.template import Template
from app.db.models.core.template_version import TemplateVersion
from app.document_engine.blueprint.models.template import TemplateConfig
from app.document_engine.orchestration.results import IngestionResult


class BlueprintState(StrEnum):
    """Informs the UI on stored blueprint state."""

    OK = "ok"
    STALE = "stale"     # loads but carries an older engine's bugs
    UNREADABLE = "unreadable"       # cannot be loaded at all


@dataclass(slots=True, frozen=True)
class RebuildResult:
    template_id: int
    name: str
    action: str
    detail: str | None = None
    diagnostics: DiagnosticCollector | None = None


class TemplateRebuildService:
    """Re-ingests template from its stored source bytes.
    
    Template blueprint is a reading of the source, not the source itself, so 
    changing engine leaves stored blueprints stale. Stored source bytes do not change, 
    filesystem isn't touched, config comes from the stored version.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = TemplateRepository(session)


    def stale(
            self,
            *,
            system: bool | None = None,
    ) -> list[Template]:

        return [
            template for template in self._repo.list(include_inactive=True)
            if (system is None or template.system is system)
            and self._stamp(template.id) != ENGINE_VERSION
        ]


    # def rebuild(self, template_id: int) -> RebuildResult:
    #     template = self._repo.get(template_id)
    #     current = self._repo.current_version(template_id)

    #     service = TemplateImportService(
    #         self._session,
    #         DbTemplateInputProvider(
    #             self._session,
    #             config=self._stored_config(template, current)
    #         ),
    #     )

    #     try:
    #         result = service.ingest_bytes(
    #             self._repo.get_source(template_id).data,
    #             name=f"{template.name}.docx",
    #         )
    #     except AppError as e:
    #         self._session.rollback()
    #         return RebuildResult(template_id, template.name, "failed", str(e))

    #     if result.diagnostics.has_errors:
    #         return RebuildResult(
    #             template_id, template.name, "failed",
    #             "the stored source no longer ingests cleanly",
    #             result.diagnostics,
    #         )

    #     self._repo.replace_blueprint(
    #         current.id, service.finalize(result), result.assets,
    #     )

    #     return RebuildResult(
    #         template_id, template.name, "rebuilt", None, result.diagnostics,
    #     )

    def state(self, template_id: int) -> BlueprintState:
        try:
            self._repo.get_blueprint(template_id)
        except BlueprintUnreadable:
            return BlueprintState.UNREADABLE
        except AppError:
            return BlueprintState.OK        # no version at all; not the service's call

        return BlueprintState.OK \
            if self._stamp(template_id) == ENGINE_VERSION \
            else BlueprintState.STALE


    def rebuild(self, template_id: int) -> RebuildResult:
        """Replace the current version's reading in place: same source, version number, corrected blueprint."""

        template = self._repo.get(template_id)
        current = self._repo.current_version(template_id)

        service, result, failure = self._reingest(template, current)
        if failure is not None:
            return failure

        result = cast(IngestionResult, result)      # result can't be None if failure is not None

        self._repo.replace_blueprint(
            current.id, service.finalize(result), result.assets,
        )

        return RebuildResult(
            template_id, template.name, "rebuilt", None, result.diagnostics,
        )


    def restore(self, template_id: int, version: int) -> RebuildResult:
        """Appends a fresh reading of an older version's source as the newest version."""

        template = self._repo.get(template_id)
        old = self._repo.version(template_id, version)

        service, result, failure = self._reingest(template, old)
        if failure is not None:
            return failure

        result = cast(IngestionResult, result)      # result can't be None if failure is not None

        service.commit_version(template_id, result)

        return RebuildResult(
            template_id, template.name, "restored", None, result.diagnostics,
        )


    def _reingest(
            self,
            template: Template,
            version: TemplateVersion,
    ) -> tuple[TemplateImportService, IngestionResult | None, RebuildResult | None]:
        """Reingests a stored source with up-to-date engine.
        
        Returns (service, result, failure); exactly one of result / failure is None.
        """

        service = TemplateImportService(
            self._session,
            DbTemplateInputProvider(
                self._session,
                config=self._stored_config(template, version),
            )
        )

        def failed(detail, diagnostics=None):
            return service, None, RebuildResult(
                template.id, template.name, "failed", detail, diagnostics,
            )

        try:
            result = service.ingest_bytes(
                self._repo.get_source(template.id, version.version).data,
                name=f"{template.name}.docx",
            )
        except AppError as e:
            self._session.rollback()
            return failed(str(e))

        if result.diagnostics.has_errors:
            return failed(
                "the stored source no longer ingests cleanly", result.diagnostics,
            )

        return service, result, None


    @staticmethod
    def _stored_config(template: Template, version: TemplateVersion) -> TemplateConfig:
        """The template's config it was ingested with. Languages are permanently baked in."""

        config = version.config
        return TemplateConfig(
            primary_language=config["primary_language"],
            secondary_language=config.get("secondary_language"),
            type=template.type,
            name=template.name,
            description=config.get("description") or "",
            append_currency=bool(config.get("append_currency"))
        )

    def _stamp(self, template_id: int) -> int:
        try:
            return self._repo.current_version(template_id).config.get("engine_version", 0)
        except AppError:
            return ENGINE_VERSION