from lxml import etree

from app.document_engine.rendering.docx.xml import qn
from app.document_engine.blueprint.models.section import SectionStyleBlueprint


def build_sect_pr(
    style: SectionStyleBlueprint,
    header_refs: list[tuple[str, str]] | None = None,
    footer_refs: list[tuple[str, str]] | None = None,
) -> etree._Element:
    
    sect_pr = etree.Element(qn("w:sectPr"))

    # (!) CT_SectPr order: headerReference, footerReference, type, pgSz, pgMar, ... , titlePg
    for htype, rid in (header_refs or []):
        ref = etree.SubElement(sect_pr, qn("w:headerReference"))
        ref.set(qn("w:type"), htype)
        ref.set(qn("r:id"), rid)        # r:id -> document.xml.rels

    for ftype, rid in (footer_refs or []):
        ref = etree.SubElement(sect_pr, qn("w:footerReference"))
        ref.set(qn("w:type"), ftype)
        ref.set(qn("r:id"), rid)        # r:id -> document.xml.rels

    etree.SubElement(sect_pr, qn("w:type")).set(qn("w:val"), style.section_type.value)

    pg_sz = etree.SubElement(sect_pr, qn("w:pgSz"))
    pg_sz.set(qn("w:w"), str(style.page_width))     # twips
    pg_sz.set(qn("w:h"), str(style.page_height))        # twips
    pg_sz.set(qn("w:orient"), style.orientation.value)

    pg_mar = etree.SubElement(sect_pr, qn("w:pgMar"))
    pg_mar.set(qn("w:top"), str(style.margins.top))
    pg_mar.set(qn("w:bottom"), str(style.margins.bottom))
    pg_mar.set(qn("w:left"), str(style.margins.left))
    pg_mar.set(qn("w:right"), str(style.margins.right))
    pg_mar.set(qn("w:footer"), str(style.margin_footer))
    pg_mar.set(qn("w:header"), str(style.margin_header))
    pg_mar.set(qn("w:gutter"), "0")     # Hardcoded value here

    if style.title_page:
        etree.SubElement(sect_pr, qn("w:titlePg"))

    return sect_pr