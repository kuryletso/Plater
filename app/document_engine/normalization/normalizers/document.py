import re

from app.document_engine.normalization.models.document import (
    NormalizedDocumentStyle,
    NormalizedNumbering,
    NormalizedNumberingDefinition,
    NormalizedNumberingInstance,
    NormalizedNumberingLevel,
    NormalizedNumberingRunStyle,
    NormalizedEmbeddedFont,
    NormalizedEmbeddedFace,
)
from app.document_engine.parser.models.styles import (
    DocumentStyle,
    NumberingLevel,
    Numbering,
    EmbeddedFace,
    EmbeddedFont,
)
from app.document_engine.enums.enums import NumberingSuffix, ParagraphAlignment

_HEX_COLOR = re.compile(r"[0-9A-Fa-f]{6}")
_FONT_KEY = re.compile(r"\{[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}")
_MAX_LEVEL = 8      # Word lists have levels 0-8


def normalize_document_style(style: DocumentStyle) -> NormalizedDocumentStyle:
    return NormalizedDocumentStyle(
        background=_page_color(style.background),
        numbering=_numbering(style.numbering),
        fonts=_fonts(style.fonts),
    )


def _page_color(value: str | None) -> str | None:
    """'auto' is no page color, and so is anything that is not a hex."""

    if value is None or not _HEX_COLOR.fullmatch(value):
        return None

    return value.upper()


def _numbering(numbering: Numbering) -> NormalizedNumbering:
    return NormalizedNumbering(
        definitions=tuple(
            NormalizedNumberingDefinition(
                definition_id=definition.definition_id,
                levels=tuple(
                    _level(level) for level in definition.levels
                    if 0 <= level.level <= _MAX_LEVEL
                )
            )
            for definition in numbering.definitions
        ),
        instances=tuple(
            NormalizedNumberingInstance(
                num_id=instance.num_id,
                definition_id=instance.definition_id,
                start_overrides=tuple(
                    (level, max(start, 0)) for level, start in instance.start_overrides
                    if 0 <= level <= _MAX_LEVEL
                )
            )
            for instance in numbering.instances
        ),
    )


def _level(level: NumberingLevel) -> NormalizedNumberingLevel:
    """What Word assumes when a level leaves something out: decimal 
    from 1, left aligned, followed by a tab.
    """

    return NormalizedNumberingLevel(
        level=level.level,
        start=max(level.start if level.start is not None else 1, 0),
        format=level.format or "decimal",
        text=level.text or "",
        alignment=_alignment(level.alignment),
        suffix=_suffix(level.suffix),
        indent_left=level.indent_left or 0,
        indent_first_line=level.indent_first_line or 0,
        style=NormalizedNumberingRunStyle(
            font_name=level.style.font_name,
            font_size=level.style.font_size,
            bold=level.style.bold,
            italic=level.style.italic,
            underline=level.style.underline,
            color=level.style.color,
        )
    )


def _alignment(value: str | None) -> ParagraphAlignment:
    try:
        return ParagraphAlignment(value) if value is not None else ParagraphAlignment.LEFT
    except ValueError:
        return ParagraphAlignment.LEFT


def _suffix(value: str | None) -> NumberingSuffix:
    try:
        return NumberingSuffix(value) if value is not None else NumberingSuffix.TAB
    except ValueError:
        return NumberingSuffix.TAB


def _fonts(fonts: tuple[EmbeddedFont, ...]) -> tuple[NormalizedEmbeddedFont, ...]:
    normalized = []
    for font in fonts:
        embedded = NormalizedEmbeddedFont(
            name=font.name,
            regular=_face(font.regular),
            bold=_face(font.bold),
            italic=_face(font.italic),
            bold_italic=_face(font.bold_italic),
        )
        if embedded != NormalizedEmbeddedFont(name=font.name):
            normalized.append(embedded)

    return tuple(normalized)


def _face(face: EmbeddedFace | None ) -> NormalizedEmbeddedFace | None:
    """A key that is all zeros or absent means the bytes are a plain font (Google Docs embedding). 
    A key that is not a GUID cannot be decoded by Word either, so that face id dropped.
    """

    if face is None:
        return None

    key = face.font_key
    if key is not None and not _FONT_KEY.fullmatch(key):
        return None
    if key is not None and not key.strip("{}-0"):
        key = None

    return NormalizedEmbeddedFace(
        asset_id=face.asset_id,
        font_key=key,
        subsetted=bool(face.subsetted),
    )