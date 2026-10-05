from dataclasses import dataclass, field

from app.assets.service import AssetCollector
from app.core.diagnostics import DiagnosticCollector
from app.document_engine.parser.archive import DocxArchive
from app.document_engine.parser.relationships import RelationshipResolver
from app.document_engine.parser.style_resolver.style_resolver import StyleResolver
from app.document_engine.parser.models.styles import Numbering


@dataclass(slots=True, frozen=True)
class ParserContext:
    archive: DocxArchive
    relationships: RelationshipResolver
    assets: AssetCollector
    style_resolver: StyleResolver
    diagnostics: DiagnosticCollector
    numbering: Numbering = Numbering()
    numbering_used: set[int] = field(default_factory=set)