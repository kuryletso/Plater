from lxml import etree

from app.document_engine.rendering.docx.xml import qn, XML_NS
from app.document_engine.parser.ooxml_properties.ooxml_properties import OOXMLRunAttributeNames
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.enums.enums import BreakType, ScriptPosition

R = OOXMLRunAttributeNames()

def build_run(
    text: str,
    style: TextStyleBlueprint,
) -> etree._Element:
    
    run = etree.Element(qn("w:r"))
    run.append(build_run_properties(style))

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


def build_field(
        instruction: str,
        cached: str,
        style: TextStyleBlueprint,
) -> list[etree._Element]:
    """A field in the complex form Word writes itself: begin, the code, separate, 
    the result, end. Every run carries the field's formatting.
    """

    def field_run(child: etree._Element) -> etree._Element:
        run = etree.Element(qn("w:r"))
        run.append(build_run_properties(style))
        run.append(child)
        return run

    def field_char(kind: str) -> etree._Element:
        char = etree.Element(qn("w:fldChar"))
        char.set(qn("w:fldCharType"), kind)
        return char

    code = etree.Element(qn("w:instrText"))
    code.set(f"{{{XML_NS}}}space", "preserve")
    code.text = f" {instruction} "

    return [
        field_run(field_char("begin")),
        field_run(code),
        field_run(field_char("separate")),
        build_run(cached or "1", style),
        field_run(field_char("end")),
    ]


def build_run_properties(style: TextStyleBlueprint) -> etree._Element:
    """<w:rPr> for a run, or for a paragraph mark inside <w:pPr>."""

    # rPr children order is important!
    # rFonts > b > i > smallCaps > strike > color > sz > highlight > u > vertAlign

    rpr = etree.Element(qn(R.properties))
    
    fonts = etree.SubElement(rpr, qn(R.fonts))
    fonts.set(qn("w:ascii"), style.font_name)
    fonts.set(qn("w:hAnsi"), style.font_name)

    if style.bold:
        etree.SubElement(rpr, qn(R.bold))
    if style.italic:
        etree.SubElement(rpr, qn(R.italic))
    if style.small_caps:
        etree.SubElement(rpr, qn(R.small_caps))
    if style.strike:
        etree.SubElement(rpr, qn(R.strike))

    etree.SubElement(rpr, qn(R.color)).set(qn("w:val"), style.color)
    etree.SubElement(rpr, qn(R.font_size)).set(qn("w:val"), str(style.font_size))       # half-points

    if style.highlight is not None:
        etree.SubElement(rpr, qn(R.highlight)).set(qn("w:val"), style.highlight.value)
    if style.underline:
        etree.SubElement(rpr, qn(R.underline)).set(qn("w:val"), "single")       # Hardcoded value here
    if style.script is not ScriptPosition.BASELINE:
        etree.SubElement(rpr, qn(R.vert_align)).set(qn("w:val"), style.script.value)

    return rpr