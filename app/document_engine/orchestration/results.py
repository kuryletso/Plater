from collections.abc import Mapping
from dataclasses import dataclass

from app.assets.service import AssetBlob
from app.core.diagnostics import DiagnosticCollector
from app.document_engine.blueprint.template_builder import TemplateDraft


@dataclass(slots=True)
class IngestionResult:
    draft: TemplateDraft
    assets: Mapping[str, AssetBlob]
    source: AssetBlob
    diagnostics: DiagnosticCollector


@dataclass(slots=True)
class RenderingResult:
    docx: bytes | None
    diagnostics: DiagnosticCollector