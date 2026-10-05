from typing import IO

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
from app.document_engine.parser.extractors.document import extract_document_style
from app.document_engine.parser.extractors.numbering import parse_numbering
from app.document_engine.parser.extractors.fonts import parse_embedded_fonts
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.relationships import RelationshipResolver
from app.document_engine.parser.style_resolver.style_resolver import StyleResolver
from app.document_engine.parser.errors import ParserFormatError
from app.document_engine.parser.models.styles import DocumentStyle

type ParsedBlock = ParagraphNode | TableNode | SectionBreakNode


class DocxParser:
    def __init__(
            self,
            source: Path | IO[bytes],
            diagnostics: DiagnosticCollector,
            *,
            name: str | None = None,
        ) -> None:
        self.archive = DocxArchive(source, name=name)
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

        try:
            numbering_root = self.archive.read_xml(DocxPaths.numbering)
        except ParserFormatError:
            numbering_root = None

        self.context = ParserContext(
            archive=self.archive,
            relationships=self.relationships,
            assets=AssetCollector(),
            style_resolver=StyleResolver(self.styles, self.doc_defaults),
            diagnostics=diagnostics,
            numbering=parse_numbering(numbering_root)
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

    def parse_document_style(self) -> DocumentStyle:
        """Use after the parse(): only the lists its paragraphs use are kept."""
        return extract_document_style(
            self.document_root,
            self.context.numbering.only(self.context.numbering_used),
            parse_embedded_fonts(self.context),
        )
    
    @property
    def assets(self) -> Mapping[str, AssetBlob]:
        return self.context.assets.bundle