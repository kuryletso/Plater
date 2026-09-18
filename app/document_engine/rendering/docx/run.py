from lxml import etree

from app.document_engine.rendering.docx.xml import qn, XML_NS
from app.document_engine.parser.ooxml_properties.ooxml_properties import OOXMLRunAttributeNames
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.enums.enums import BreakType

R = OOXMLRunAttributeNames()

def build_run(
    text: str,
    style: TextStyleBlueprint,
) -> etree._Element:
    
    # rPr children order is important!
    # rFonts > b > i > color > sz > u

    run = etree.Element(qn("w:r"))
    rpr = etree.SubElement(run, qn(R.properties))

    fonts = etree.SubElement(rpr, qn(R.fonts))
    fonts.set(qn("w:ascii"), style.font_name)
    fonts.set(qn("w:hAnsi"), style.font_name)

    if style.bold:
        etree.SubElement(rpr, qn(R.bold))
    if style.italic:
        etree.SubElement(rpr, qn(R.italic))

    etree.SubElement(rpr, qn(R.color)).set(qn("w:val"), style.color)
    etree.SubElement(rpr, qn(R.font_size)).set(qn("w:val"), str(style.font_size))       # half-points

    if style.underline:
        etree.SubElement(rpr, qn(R.underline)).set(qn("w:val"), "single")       # Hardcoded value here

    ###### replaced with the `for line_idx, line ...` loop to properly emit tabs
    # segments = text.split("\n")
    # for idx, segment in enumerate(segments):
    #     if idx > 0:
    #         etree.SubElement(run, qn("w:br"))
    #     if segment:
    #         t = etree.SubElement(run, qn("w:t"))
    #         t.set(f"{{{XML_NS}}}space", "preserve")     # Hardcoded value here
    #         t.text = segment

    for line_idx, line in enumerate(text.split("\n")):
        if line_idx:
            etree.SubElement(run, qn("w:br"))

        for tab_idx, chunk in enumerate(line.split("\t")):
            if tab_idx:
                etree.SubElement(run, qn("w:tab"))
            if chunk:
                t = etree.SubElement(run, qn("w:t"))
                t.set(f"{{{XML_NS}}}space", "preserve")     # Hardcoded value here
                t.text = chunk

    return run


def build_break_run(kind: BreakType) -> etree._Element:
    """Run that only holds a page or column break."""

    run = etree.Element(qn("w:r"))
    etree.SubElement(run, qn("w:br")).set(qn("w:type"), kind.value)
    return run