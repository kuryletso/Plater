from lxml.etree import _Element

from app.document_engine.enums.enums import HeaderFooterType
from app.document_engine.parser.extractors.header_footer import parse_header_footer_by_id
from app.document_engine.parser.models.blocks import SectionBreakNode
from app.document_engine.parser.models.header_footer import HeaderFooterNode
from app.document_engine.parser.models.styles import SectionStyle, Margins
from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_attr, get_int_attr
from app.document_engine.parser.utils.get_relationship import get_relationship_id


def parse_section(section: _Element, context: ParserContext) -> SectionBreakNode:
    section_type = None
    orientation = None
    page_width = None
    page_height = None
    margin_header = None
    margin_footer = None
    margin_top = None
    margin_bottom = None
    margin_left = None
    margin_right = None

    type_node = section.find("w:type", NS)
    if type_node is not None:
        section_type = get_attr(type_node, "val")

    page_size = section.find("w:pgSz", NS)
    if page_size is not None:
        orientation = get_attr(page_size, "orient")
        page_width = get_int_attr(page_size, "w")
        page_height = get_int_attr(page_size, "h")

    page_margins = section.find("w:pgMar", NS)
    if page_margins is not None:
        margin_header = get_int_attr(page_margins, "header")
        margin_footer = get_int_attr(page_margins, "footer")
        margin_top = get_int_attr(page_margins, "top")
        margin_bottom = get_int_attr(page_margins, "bottom")
        margin_left = get_int_attr(page_margins, "left")
        margin_right = get_int_attr(page_margins, "right")

    headers: dict[HeaderFooterType, HeaderFooterNode] = {}
    footers: dict[HeaderFooterType, HeaderFooterNode] = {}

    for header_reference in section.findall("w:headerReference", NS):
        reference_type_attr = get_attr(header_reference, "type")
        try:
            reference_type = HeaderFooterType(reference_type_attr)
        except ValueError:
            continue

        relationship_id = get_relationship_id(header_reference)
        if relationship_id is None:
            continue

        header = parse_header_footer_by_id(
            relationship_id,
            reference_type,
            context=context, # TODO: headers/footers have dedicated .rels; currently reuses document.xml rels which breaks meadia/hyperlinks inside headers/footers
        )
        if header is not None:
            headers[header.type] = header

    for footer_reference in section.findall("w:footerReference", NS):
        reference_type_attr = get_attr(footer_reference, "type")
        try:
            reference_type = HeaderFooterType(reference_type_attr)
        except ValueError:
            continue

        relationship_id = get_relationship_id(footer_reference)
        if relationship_id is None:
            continue

        footer = parse_header_footer_by_id(
            relationship_id,
            reference_type,
            context=context, # TODO: headers/footers have dedicated .rels; currently reuses document.xml rels which breaks meadia/hyperlinks inside headers/footers
        )
        if footer is not None:
            footers[footer.type] = footer

    return SectionBreakNode(
        style=SectionStyle(
            section_type=section_type,
            page_width=page_width,
            page_height=page_height,
            orientation=orientation,
            margin_header=margin_header,
            margin_footer=margin_footer,
            margins=Margins(
                top=margin_top,
                bottom=margin_bottom,
                left=margin_left,
                right=margin_right,
            ),
        ),
        headers=headers,
        footers=footers,
    )