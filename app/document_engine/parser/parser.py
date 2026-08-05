from collections.abc import Mapping
from pathlib import Path

from app.assets.service import AssetCollector, AssetBlob
from app.core.diagnostics import DiagnosticCollector
from app.document_engine.parser.archive import DocxArchive, DocxPaths
from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.models.blocks import ParagraphNode, TableNode, SectionBreakNode
from app.document_engine.parser.extractors.blocks import iter_blocks
from app.document_engine.parser.extractors.paragraphs import parse_paragraph
from app.document_engine.parser.extractors.sections import parse_section
from app.document_engine.parser.extractors.tables import parse_table
from app.document_engine.parser.extractors.styles import parse_styles
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.relationships import RelationshipResolver
from app.document_engine.parser.style_resolver.style_resolver import StyleResolver
from app.document_engine.parser.errors import ParserFormatError

type ParsedBlock = ParagraphNode | TableNode | SectionBreakNode


class DocxParser:
    def __init__(
            self,
            path: Path,
            diagnostics: DiagnosticCollector,
        ) -> None:
        self.archive = DocxArchive(path)
        self.document_root = self.archive.read_xml(DocxPaths.document)

        try:
            self.styles_root = self.archive.read_xml(DocxPaths.styles)
        except ParserFormatError:
            self.styles_root = None
        self.styles = parse_styles(self.styles_root) \
            if self.styles_root is not None else {}
        self.doc_defaults = self.styles_root.find("w:docDefaults", NS) \
            if self.styles_root is not None else None

        try:
            rel_root = self.archive.read_xml(DocxPaths.relationships)
        except ParserFormatError:
            rel_root = None
        self.relationships = RelationshipResolver(rel_root)

        self.context = ParserContext(
            archive=self.archive,
            relationships=self.relationships,
            assets=AssetCollector(),
            style_resolver=StyleResolver(self.styles, self.doc_defaults),
            diagnostics=diagnostics,
        )

    def __enter__(self): return self

    def __exit__(self, *_): self.archive.close()

    def parse(self) -> list[ParsedBlock]:
        body = self.document_root.find("w:body", NS)

        if body is None:
            raise ParserFormatError(
                "Document body not found."
            )
        
        result = []

        for block_type, node in iter_blocks(body):
            match block_type:
                case "paragraph":
                    result.append(parse_paragraph(node, self.context))
                case "table":
                    result.append(parse_table(node, self.context))
                case "section":
                    result.append(parse_section(node, self.context))

        return result
    
    @property
    def assets(self) -> Mapping[str, AssetBlob]:
        return self.context.assets.bundle