from pathlib import Path

from app.core.diagnostics import DiagnosticCollector
from app.core.errors import AppError, Severity
from app.assets.hashing import hash_bytes
from app.assets.service import AssetBlob
from app.assets.mime import detect_mime_type

from app.document_engine.parser.parser import DocxParser
from app.document_engine.normalization.structural_normalizer import StructuralNormalizer
from app.document_engine.blueprint.template_builder import TemplateBuilder, TemplateDraft
from app.document_engine.blueprint.models.template import TemplateBlueprint

from app.document_engine.rendering.context import RenderContext
from app.document_engine.rendering.ports import AssetProvider
from app.document_engine.rendering.validate import validate_context
from app.document_engine.rendering.resolve.resolver import DocumentResolver
from app.document_engine.rendering.docx.emitter import DocxEmitter

from .ports import TemplateInputProvider
from .results import IngestionResult, RenderingResult
from .errors import IngestionError, RenderingFailedError

from app.document_engine.enums.enums import ResolveMode


class TemplateIngestionPipeline:
    def __init__(
        self,
        inputs: TemplateInputProvider,
    ) -> None:
        self._inputs = inputs


    def ingest(
        self,
        path: Path,
    ) -> IngestionResult:
        
        diagnostics = DiagnosticCollector()
        source_bytes = Path(path).read_bytes()
        source = AssetBlob(
            sha256=hash_bytes(source_bytes),
            mime_type=detect_mime_type(Path(path).name),
            data=source_bytes,
        )

        try:
            with DocxParser(path, diagnostics=diagnostics) as parser:
                parsed = parser.parse()
                assets = dict(parser.assets)

            normalized = StructuralNormalizer.normalize(parsed, diagnostics)

            draft = TemplateBuilder().build_draft(
                tuple(normalized),
                default_config=self._inputs.default_template_config(),
                placeholder_defaults=self._inputs.placeholder_defaults(),
                languages=self._inputs.languages(),
                diagnostics=diagnostics,
            )

        except AppError as e:
            diagnostics.record(e.as_diagnostic(Severity.ERROR))
            raise IngestionError(
                f"Template ingestion failed in {e.layer}: {e}.",
                user_message="The template could not be processed.",
                context={"path": str(path), "cause": e.code},
            ) from e
        
        return IngestionResult(
            draft=draft,
            assets=assets,
            source=source,
            diagnostics=diagnostics,
        )
    
    def finalize(
        self,
        draft: TemplateDraft,
    ) -> TemplateBlueprint:
        
        return TemplateBuilder().save_draft(draft)
    


class TemplateRenderingPipeline:
    def __init__(self, assets: AssetProvider) -> None:
        self._assets = assets

    def render(
        self,
        blueprint: TemplateBlueprint,
        context: RenderContext,
    ) -> RenderingResult:
        
        diagnostics = DiagnosticCollector()

        if not validate_context(blueprint, context, diagnostics):
            return RenderingResult(docx=None, diagnostics=diagnostics)
        
        try:
            resolved = DocumentResolver(
                context,
                self._assets,
                diagnostics,
            ).resolve(blueprint)
            docx = DocxEmitter(diagnostics).emit(resolved)
        except AppError as e:
            diagnostics.record(e.as_diagnostic(Severity.ERROR))
            raise RenderingFailedError(
                f"Rendering failed in {e.layer}: {e}:",
                user_message="The document could not be rendered.",
                context={"cause": e.code},
            ) from e
        
        return RenderingResult(docx=docx, diagnostics=diagnostics)


    def render_raw(
            self,
            blueprint: TemplateBlueprint,
    ) -> RenderingResult:
        """Render with placeholders left as '{{ key }} for export and preview."""

        diagnostics = DiagnosticCollector()

        try:
            resolved = DocumentResolver(
                RenderContext(),
                self._assets,
                diagnostics,
                mode=ResolveMode.KEYS,
            ).resolve(blueprint)
            docx = DocxEmitter(diagnostics).emit(resolved)

        except AppError as e:
            diagnostics.record(e.as_diagnostic(Severity.ERROR))
            raise RenderingFailedError(
                f"Raw rendering failed in {e.layer}: {e}.",
                user_message="The template could not be rendered.",
                context={"cause": e.code},
            ) from e

        return RenderingResult(docx=docx, diagnostics=diagnostics)