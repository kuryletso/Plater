from lxml.etree import _Element

from app.document_engine.parser.models.styles import DocumentStyle, Numbering, EmbeddedFont
from app.document_engine.parser.ooxml_properties.ooxml_properties import OOXMLDocumentAttributeNames
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_attr


def extract_document_style(
        document_root: _Element,
        numbering: Numbering,
        fonts: tuple[EmbeddedFont, ...],
) -> DocumentStyle:
    """<w:background> is the first child of <w:document> outside the body. 
    Only its color is read. A theme color, gradient or picture fill has no plain color.
    """

    background = document_root.find(OOXMLDocumentAttributeNames.background, NS)

    return DocumentStyle(
        background=get_attr(background, "color") if background is not None else None,
        numbering=numbering,
        fonts=fonts,
    )