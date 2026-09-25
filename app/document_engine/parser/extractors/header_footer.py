from dataclasses import replace

from app.document_engine.parser.extractors.paragraphs import parse_paragraph 
from app.document_engine.parser.extractors.tables import parse_table 
from app.document_engine.parser.models.blocks import BlockNode
from app.document_engine.parser.models.header_footer import HeaderFooterNode
from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.relationships import part_relationships
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.errors import ParserFormatError

from app.document_engine.enums.enums import HeaderFooterType


def parse_header_footer_by_id(
    relationship_id: str,
    _type: HeaderFooterType,
    *,
    context: ParserContext,
) -> HeaderFooterNode | None:
    
    relationship = context.relationships.get(relationship_id)
    if relationship is None:
        return None
    
    try:
        root = context.archive.read_xml(relationship.target)
    except ParserFormatError:
        return None

    part_context = replace(
        context,
        relationships=part_relationships(context.archive, relationship.target)
    )
    
    blocks: list[BlockNode] = []

    for child in root:
        tag = child.tag

        if tag == f"{{{NS['w']}}}p":
            paragraph = parse_paragraph(child, part_context)
            blocks.append(paragraph)

        elif tag == f"{{{NS['w']}}}tbl":
            table = parse_table(child, part_context)
            blocks.append(table)

    return HeaderFooterNode(
        type=_type,
        blocks=blocks,
    )