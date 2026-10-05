from dataclasses import dataclass

from app.document_engine.enums.enums import ParagraphAlignment, NumberingSuffix


@dataclass(slots=True, frozen=True)
class NormalizedNumberingRunStyle:
    """Formatting that the number sets over the paragraph mark. 
    None keeps the mark's one.
    """

    font_name: str | None = None
    font_size: int | None = None        # half-points
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: str | None = None


@dataclass(slots=True, frozen=True)
class NormalizedNumberingLevel:
    level: int
    start: int
    format: str
    text: str
    alignment: ParagraphAlignment
    suffix: NumberingSuffix
    indent_left: int        # twips
    indent_first_line: int      # twips, negative is a hanging indent
    style: NormalizedNumberingRunStyle


@dataclass(slots=True, frozen=True)
class NormalizedNumberingDefinition:
    definition_id: int
    levels: tuple[NormalizedNumberingLevel, ...]


@dataclass(slots=True, frozen=True)
class NormalizedNumberingInstance:
    num_id: int
    definition_id: int
    start_overrides: tuple[tuple[int, int], ...] = ()       # (level, start)


@dataclass(slots=True, frozen=True)
class NormalizedNumbering:
    definitions: tuple[NormalizedNumberingDefinition, ...] = ()
    instances: tuple[NormalizedNumberingInstance, ...] = ()


@dataclass(slots=True, frozen=True)
class NormalizedEmbeddedFace:
    asset_id: str
    font_key: str | None        # GUID the bytes are obfuscated with; None is a plain font
    subsetted: bool


@dataclass(slots=True, frozen=True)
class NormalizedEmbeddedFont:
    name: str
    regular: NormalizedEmbeddedFace | None = None
    bold: NormalizedEmbeddedFace | None = None
    italic: NormalizedEmbeddedFace | None = None
    bold_italic: NormalizedEmbeddedFace | None = None


@dataclass(slots=True, frozen=True)
class NormalizedDocumentStyle:
    background: str | None = None       # page color, uppercase hex; None is no color
    numbering: NormalizedNumbering = NormalizedNumbering()
    fonts: tuple[NormalizedEmbeddedFont, ...] = ()