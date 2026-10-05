from lxml import etree

from app.document_engine.rendering.docx.xml import qn, WORD_NSMAP


def build_settings(
        *,
        even_and_odd_headers: bool,
        embed_fonts: bool,
        display_background: bool,
) -> etree._Element:

    settings = etree.Element(qn("w:settings"), nsmap=WORD_NSMAP)

    # (!) CT_Settings order:
    # displayBackgroundShape > embedTrueTypeFonts > evenAndOddHeaders
    if display_background:
        etree.SubElement(settings, qn("w:displayBackgroundShape"))
    if embed_fonts:
        etree.SubElement(settings, qn("w:embedTrueTypeFonts"))
    if even_and_odd_headers:
        etree.SubElement(settings, qn("w:evenAndOddHeaders"))
    
    return settings