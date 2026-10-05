from lxml import etree

from app.document_engine.rendering.docx.xml import qn
from app.document_engine.rendering.docx.run import build_run_properties
from app.document_engine.parser.ooxml_properties.ooxml_properties import OOXMLParagraphAttributeNames
from app.document_engine.blueprint.models.paragraph import (
    ParagraphStyleBlueprint,
    ParagraphBordersBlueprint,
)

P = OOXMLParagraphAttributeNames()

BORDER_SIDES = ("top", "left", "bottom", "right", "between")        # CT_PBdr order


def build_paragraph(
    runs: list[etree._Element],
    style: ParagraphStyleBlueprint,
) -> etree._Element:
    
    # pPr children order is important!
    # keepNext > pageBreakBefore > numPr > pBdr > spacing > ind > jc > rPr

    p = etree.Element(qn("w:p"))
    ppr = etree.SubElement(p, qn(P.properties))

    if style.keep_next:
        etree.SubElement(ppr, qn(P.keep_next))
    if style.page_break_before:
        etree.SubElement(ppr, qn(P.page_break_before))

    if style.numbering is not None:
        # (!) CT_NumPr order: ilvl > numId
        num_pr = etree.SubElement(ppr, qn(P.numbering))
        etree.SubElement(num_pr, qn("w:ilvl")).set(qn("w:val"), str(style.numbering.level))
        etree.SubElement(num_pr, qn("w:numId")).set(qn("w:val"), str(style.numbering.num_id))

    if style.borders is not None:
        ppr.append(_build_borders(style.borders))

    spacing = etree.SubElement(ppr, qn(P.spacing))      # twips
    spacing.set(qn("w:before"), str(style.spacing_before))
    spacing.set(qn("w:after"), str(style.spacing_after))
    spacing.set(qn("w:line"), str(style.line_spacing))
    spacing.set(qn("w:lineRule"), style.line_rule.value)

    ind = etree.SubElement(ppr, qn(P.indent))
    ind.set(qn("w:left"), str(style.indent_left))
    ind.set(qn("w:right"), str(style.indent_right))
    if style.indent_first_line < 0:
        ind.set(qn("w:hanging"), str(-style.indent_first_line))
    elif style.indent_first_line > 0:
        ind.set(qn("w:firstLine"), str(style.indent_first_line))

    etree.SubElement(ppr, qn(P.alignment)).set(qn("w:val"), style.alignment.value)

    if style.mark is not None:
        ppr.append(build_run_properties(style.mark))

    for run in runs:
        p.append(run)

    return p


def _build_borders(borders: ParagraphBordersBlueprint) -> etree._Element:
    pbdr = etree.Element(qn(P.borders))

    for side in BORDER_SIDES:
        border = getattr(borders, side)
        if border is None:
            continue

        e = etree.SubElement(pbdr, qn(f"w:{side}"))
        e.set(qn("w:val"), border.style.value)
        e.set(qn("w:sz"), str(border.size))     # eights of a point
        e.set(qn("w:space"), str(border.space))     # points
        e.set(qn("w:color"), border.color)

    return pbdr