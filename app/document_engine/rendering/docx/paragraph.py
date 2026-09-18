from lxml import etree

from app.document_engine.rendering.docx.xml import qn
from app.document_engine.parser.ooxml_properties.ooxml_properties import OOXMLParagraphAttributeNames
from app.document_engine.blueprint.models.paragraph import ParagraphStyleBlueprint


P = OOXMLParagraphAttributeNames()

def build_paragraph(
    runs: list[etree._Element],
    style: ParagraphStyleBlueprint,
) -> etree._Element:
    
    # pPr children order is important!
    # keepNext > pageBreakBefore > spacing > ind > jc

    p = etree.Element(qn("w:p"))
    ppr = etree.SubElement(p, qn(P.properties))

    if style.keep_next:
        etree.SubElement(ppr, qn(P.keep_next))
    if style.page_break_before:
        etree.SubElement(ppr, qn(P.page_break_before))

    spacing = etree.SubElement(ppr, qn(P.spacing))      # twips
    spacing.set(qn("w:before"), str(style.spacing_before))
    spacing.set(qn("w:after"), str(style.spacing_after))
    spacing.set(qn("w:line"), str(style.line_spacing))
    spacing.set(qn("w:lineRule"), style.line_rule.value)

    ind = etree.SubElement(ppr, qn(P.indent))
    ind.set(qn("w:left"), str(style.indent_left))
    ind.set(qn("w:right"), str(style.indent_right))

    etree.SubElement(ppr, qn(P.alignment)).set(qn("w:val"), style.alignment.value)

    for run in runs:
        p.append(run)

    return p