from lxml import etree

from app.document_engine.rendering.docx.xml import qn
from app.document_engine.enums.enums import TableWidthType
from app.document_engine.blueprint.models.margins import MarginsBlueprint
from app.document_engine.blueprint.models.table import (
    TableStyleBlueprint,
    RowStyleBlueprint,
    CellStyleBlueprint,
    TableBorderBlueprint,
)

DEFAULT_COL_WIDTH = 2400        # twips, Hardcoded value here


def _build_margins(
    tag: str,
    m: MarginsBlueprint,
) -> etree._Element:
    
    el = etree.Element(qn(tag))
    for side, val in (
        ("w:top", m.top),
        ("w:bottom", m.bottom),
        ("w:left", m.left),
        ("w:right", m.right),
    ):
        e = etree.SubElement(el, qn(side))
        e.set(qn("w:w"), str(val))
        e.set(qn("w:type"), "dxa")

    return el


def _build_border(
    tag: str,
    b: TableBorderBlueprint,
) -> etree._Element:
    
    e = etree.Element(qn(tag))
    e.set(qn("w:val"), b.style.value)
    e.set(qn("w:sz"), str(b.size))
    e.set(qn("w:color"), b.color)
    e.set(qn("w:space"), "0")       # Hardcoded value here

    return e


def _build_tbl_borders(
    style: TableStyleBlueprint,
) -> etree._Element:
    
    borders = etree.Element(qn("w:tblBorders"))

    # (!) CT_TblBorders order: top, left, bottom, right, insideH, insideV
    borders.append(_build_border("w:top", style.border_top))
    borders.append(_build_border("w:left", style.border_left))
    borders.append(_build_border("w:bottom", style.border_bottom))
    borders.append(_build_border("w:right", style.border_right))
    borders.append(_build_border("w:insideH", style.border_inside_h))
    borders.append(_build_border("w:insideV", style.border_inside_v))

    return borders


def _build_tbl_pr(
    style: TableStyleBlueprint,
) -> etree._Element:
    
    tbl_pr = etree.Element(qn("w:tblPr"))

    # (!) CT_TblPr order: tblW, tblBorders, tblLayout, tblCellMar
    w = etree.SubElement(tbl_pr, qn("w:tblW"))
    w.set(qn("w:w"), str(style.width.value or 0))
    w.set(qn("w:type"), style.width.type.value)

    tbl_pr.append(_build_tbl_borders(style))

    layout = etree.SubElement(tbl_pr, qn("w:tblLayout"))
    layout.set(qn("w:type"), "autofit" if style.autofit else "fixed")

    tbl_pr.append(_build_margins("w:tblCellMar", style.margins))

    return tbl_pr


def _build_tbl_grid(
    columns: int,
    style: TableStyleBlueprint,
) -> etree._Element:
    
    grid = etree.Element(qn("w:tblGrid"))

    widths = style.column_widths

    # The source grid only applies when the column count matches;
    # whole-table placeholder sets its own due to dynamic nature (tax columns is optional)
    if len(widths) != columns:
        if style.width.type == TableWidthType.DXA and style.width.value:
            col_w = style.width.value // columns
        else:
            col_w = DEFAULT_COL_WIDTH
        widths = (col_w,) * columns

    for width in widths:
        etree.SubElement(grid, qn("w:gridCol")).set(qn("w:w"), str(width))

    return grid


def _build_tc_borders(
        style: CellStyleBlueprint,
) -> etree._Element | None:
    """Only emitter for sides the template set, otherwise the table's borders inherit."""

    sides = (
        ("w:top", style.border_top),
        ("w:left", style.border_left),
        ("w:bottom", style.border_bottom),
        ("w:right", style.border_right),
    )

    if all(border is None for _, border in sides):
        return None

    borders = etree.Element(qn("w:tcBorders"))
    for tag, border in sides:
        if border is not None:
            borders.append(_build_border(tag, border))

    return borders


def build_cell(
    blocks: list[etree._Element],
    style: CellStyleBlueprint,
) -> etree._Element:
    
    tc = etree.Element(qn("w:tc"))
    tc_pr = etree.SubElement(tc, qn("w:tcPr"))

    # (!) CT_TcPr order: gridSpan, tcBorders, shd, tcMar, vAlign
    if style.grid_span > 1:
        etree.SubElement(tc_pr,qn("w:gridSpan")).set(qn("w:val"), str(style.grid_span))

    borders = _build_tc_borders(style)
    if borders is not None:
        tc_pr.append(borders)
    
    shd = etree.SubElement(tc_pr, qn("w:shd"))
    shd.set(qn("w:val"), style.shading.value)
    shd.set(qn("w:fill"), style.shading_fill)

    tc_pr.append(_build_margins("w:tcMar", style.margins))
    etree.SubElement(tc_pr, qn("w:vAlign")).set(qn("w:val"), style.v_alignment.value)

    if blocks:
        for block in blocks:
            tc.append(block)
    else:
        etree.SubElement(tc, qn("w:p"))

    return tc



def build_row(
    cells: list[etree._Element],
    style: RowStyleBlueprint,
) -> etree._Element:
    
    tr = etree.Element(qn("w:tr"))
    tr_pr = etree.SubElement(tr, qn("w:trPr"))

    # (!) CT_TrPr order: trHeight, tblHeader
    if style.height:
        h = etree.SubElement(tr_pr, qn("w:trHeight"))
        h.set(qn("w:val"), str(style.height))
        h.set(qn("w:hRule"), "atLeast")     # Hardcoded value here
    if style.header:
        etree.SubElement(tr_pr, qn("w:tblHeader"))

    for cell in cells:
        tr.append(cell)
    return tr



def build_table(
    rows: list[etree._Element],
    style: TableStyleBlueprint,
    columns: int,
) -> etree._Element:
    
    tbl = etree.Element(qn("w:tbl"))
    tbl.append(_build_tbl_pr(style))
    tbl.append(_build_tbl_grid(columns, style))     # MUST come right after tblPr, before rows

    for row in rows:
        tbl.append(row)
    return tbl