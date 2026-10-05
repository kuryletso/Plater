from lxml import etree

from app.document_engine.rendering.docx.xml import qn, WORD_NSMAP
from app.document_engine.rendering.resolve.models import ResolvedFont

PLAIN_FONT_KEY = "{00000000-0000-0000-0000-000000000000}"

# (!) CT_Font order:
# embedRegular > embedBold > embedItalic > embedBoldItalic
EMBED_TAGS = {
    "regular": "w:embedRegular",
    "bold": "w:embedBold",
    "italic": "w:embedItalic",
    "bold_italic": "w:embedBoldItalic",
}

def font_extension(font_key: str | None) -> str:
    return "odttf" if font_key else "ttf"


def build_font_table(fonts: list[tuple[ResolvedFont, list[str]]]) -> etree._Element:
    """word/fontTable.xml . Each font comes with the relationship ids of its faces, 
    in face order. The ids belong to the font table's own relationships.
    """

    root = etree.Element(qn("w:fonts"), nsmap=WORD_NSMAP)

    for font, relationship_ids in fonts:
        element = etree.SubElement(root, qn("w:font"))
        element.set(qn("w:name"), font.name)

        for face, relationship_id in zip(font.faces, relationship_ids):
            embed = etree.SubElement(element, qn(EMBED_TAGS[face.kind]))
            embed.set(qn("r:id"), relationship_id)
            embed.set(qn("w:fontKey"), face.font_key or PLAIN_FONT_KEY)
            embed.set(qn("w:subsetted"), "1" if face.subsetted else "0")

    return root