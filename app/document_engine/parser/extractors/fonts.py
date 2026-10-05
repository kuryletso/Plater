from pathlib import PurePosixPath

from lxml.etree import _Element

from app.document_engine.parser.models.styles import EmbeddedFont, EmbeddedFace
from app.document_engine.parser.archive import DocxPaths
from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.relationships import RelationshipResolver, part_relationships
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_attr, get_bool_attr
from app.document_engine.parser.utils.get_relationship import get_relationship_id
from app.document_engine.parser.errors import ParserFormatError
from app.core.errors import Layer

MAX_FONT_SIZE_BYTES = 24 * 1024 * 1024      # 24 MB

FACES = (
    ("regular", "w:embedRegular"),
    ("bold", "w:embedBold"),
    ("italic", "w:embedItalic"),
    ("bold_italic", "w:embedBoldItalic"),
)

def parse_embedded_fonts(context: ParserContext) -> tuple[EmbeddedFont, ...]:
    """Fonts carried by template. word/fontTable.xml names each embedded face 
    through a relationship of its own part, never the document's one. 
    
    The bytes are kept exactly as stored, with their key: Word obfuscates a font with a GUID, 
    Google Docx stores it plain under an all-zero one. Neither is decoded.
    """

    try:
        root = context.archive.read_xml(DocxPaths.font_table)
    except ParserFormatError:
        return ()

    relationships = part_relationships(context.archive, DocxPaths.font_table)

    fonts = []
    for font in root.findall("w:font", NS):
        name = get_attr(font, "name")
        if not name:
            continue

        faces = {
            field: _face(font.find(tag, NS), name, relationships, context)
            for field, tag in FACES
        }
        if any(faces.values()):
            fonts.append(EmbeddedFont(name=name, **faces))

    return tuple(fonts)


def _face(
        node: _Element | None,
        font_name: str,
        relationships: RelationshipResolver,
        context: ParserContext,
) -> EmbeddedFace | None:

    if node is None:
        return None

    relationship_id = get_relationship_id(node)
    relationship = relationships.get(relationship_id) if relationship_id else None

    if relationship is None \
    or relationship.is_external \
    or not relationship.type.endswith("/font") \
    or not context.archive.exists(relationship.target):
        context.diagnostics.warn(
            Layer.PARSER,
            "embedded_font_missing",
            f"An embedded face of '{font_name}' could not be found in the file; it was not embedded.",
            font=font_name,
            relationship_id=relationship_id,
        )
        return None

    target = relationship.target
    if context.archive.get_uncompressed_size(target) > MAX_FONT_SIZE_BYTES:
        context.diagnostics.warn(
            Layer.PARSER,
            "embedded_font_too_large",
            f"An embedded face of '{font_name}' exceed the size limit; it was not embedded.",
            font=font_name,
            target=target,
        )
        return None

    return EmbeddedFace(
        asset_id=context.assets.add(
            filename=PurePosixPath(target).name,
            data=context.archive.read_bytes(target),
        ),
        font_key=get_attr(node, "fontKey"),
        subsetted=get_bool_attr(node, "subsetted"),
    )