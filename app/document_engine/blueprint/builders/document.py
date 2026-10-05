from app.document_engine.blueprint.models.document import (
    DocumentStyleBlueprint,
    NumberingBlueprint,
    NumberingInstanceBlueprint,
    NumberingDefinitionBlueprint,
    NumberingLevelBlueprint,
    NumberingRunStyleBlueprint,
    EmbeddedFontBlueprint,
    EmbeddedFaceBlueprint,
)
from app.document_engine.normalization.models.document import (
    NormalizedDocumentStyle,
    NormalizedNumbering,
    NormalizedNumberingLevel,
    NormalizedEmbeddedFace,
    NormalizedEmbeddedFont,
)


def document_style_bp_from_normalized(
        style: NormalizedDocumentStyle,
) -> DocumentStyleBlueprint:

    return DocumentStyleBlueprint(
        background=style.background,
        numbering=numbering_bp_from_normalized(style.numbering),
        fonts=tuple(_font_bp(font) for font in style.fonts),
    )


def numbering_bp_from_normalized(
        numbering: NormalizedNumbering,
) -> NumberingBlueprint:

    return NumberingBlueprint(
        definitions=tuple(
            NumberingDefinitionBlueprint(
                definition_id=definition.definition_id,
                levels=tuple(_level_bp(level) for level in definition.levels),
            )
            for definition in numbering.definitions
        ),
        instances=tuple(
            NumberingInstanceBlueprint(
                num_id=instance.num_id,
                definition_id=instance.definition_id,
                start_overrides=instance.start_overrides,
            )
            for instance in numbering.instances
        ),
    )


def _level_bp(level: NormalizedNumberingLevel) -> NumberingLevelBlueprint:
    return NumberingLevelBlueprint(
        level=level.level,
        start=level.start,
        format=level.format,
        text=level.text,
        alignment=level.alignment,
        suffix=level.suffix,
        indent_left=level.indent_left,
        indent_first_line=level.indent_first_line,
        style=NumberingRunStyleBlueprint(
            font_name=level.style.font_name,
            font_size=level.style.font_size,
            bold=level.style.bold,
            italic=level.style.italic,
            underline=level.style.underline,
            color=level.style.color,
        ),
    )


def _font_bp(font: NormalizedEmbeddedFont) -> EmbeddedFontBlueprint:
    return EmbeddedFontBlueprint(
        name=font.name,
        regular=_face_bp(font.regular),
        bold=_face_bp(font.bold),
        italic=_face_bp(font.italic),
        bold_italic=_face_bp(font.bold_italic),
    )


def _face_bp(face: NormalizedEmbeddedFace | None) -> EmbeddedFaceBlueprint | None:
    if face is None:
        return None

    return EmbeddedFaceBlueprint(
        asset_id=face.asset_id,
        font_key=face.font_key,
        subsetted=face.subsetted,
    )