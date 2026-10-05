from lxml import etree

from app.document_engine.rendering.docx.xml import qn
from app.document_engine.blueprint.models.section import SectionStyleBlueprint, ColumnsBlueprint


def build_sect_pr(
    style: SectionStyleBlueprint,
    header_refs: list[tuple[str, str]] | None = None,
    footer_refs: list[tuple[str, str]] | None = None,
) -> etree._Element:
    
    sect_pr = etree.Element(qn("w:sectPr"))

    # (!) CT_SectPr order:
    # headerReference, footerReference, type, pgSz, pgMar, ... , cols, ... titlePg
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

    if style.columns is not None:
        sect_pr.append(_build_cols(style.columns))

    if style.title_page:
        etree.SubElement(sect_pr, qn("w:titlePg"))

    return sect_pr


def _build_cols(columns: ColumnsBlueprint) -> etree._Element:
    """Equal columns are written by Word standard: a count, a space, no <w:col> children. 
    Explicit widths need equalWidth="0" and one <w:col> each.
    """

    cols = etree.Element(qn("w:cols"))
    cols.set(qn("w:num"), str(columns.count))
    cols.set(qn("w:space"), str(columns.space))     # twips
    if columns.separator:
        cols.set(qn("w:sep"), "1")

    if columns.widths:
        cols.set(qn("w:equalWidth"), "0")
        for column in columns.widths:
            col = etree.SubElement(cols, qn("w:col"))
            col.set(qn("w:w"), str(column.width))
            col.set(qn("w:space"), str(column.space))

    return cols