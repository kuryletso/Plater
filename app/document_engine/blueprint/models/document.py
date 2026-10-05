from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.enums.enums import ParagraphAlignment, NumberingSuffix


class NumberingRunStyleBlueprint(BlueprintBase):
    """Formatting the number sets over the paragraph mark's one. None keeps the mark's one."""

    font_name: str | None = None
    font_size: int | None = None        # half-points
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: str | None = None


class NumberingLevelBlueprint(BlueprintBase):
    level: int
    start: int = 1
    format: str = "decimal"     # ST_NumberFormat
    text: str = ""      # "%1." or the bullet character
    alignment: ParagraphAlignment = ParagraphAlignment.LEFT
    suffix: NumberingSuffix = NumberingSuffix.TAB
    indent_left: int = 0        # twips
    indent_first_line: int = 0      # twips, negative means a hanging indent
    style: NumberingRunStyleBlueprint = NumberingRunStyleBlueprint()


class NumberingDefinitionBlueprint(BlueprintBase):
    """<w:abstractNum> , how a list is drawn."""

    definition_id: int
    levels: tuple[NumberingLevelBlueprint, ...] = ()


class NumberingInstanceBlueprint(BlueprintBase):
    """<w:num>, what paragraphs name. Kept apart from the definition, since 
    in Word instances of one definition continue oen count unless an override restarts it.
    """

    num_id: int
    definition_id: int
    start_overrides: tuple[tuple[int, int], ...] = ()       # (level, start)


class NumberingBlueprint(BlueprintBase):
    definitions: tuple[NumberingDefinitionBlueprint, ...] = ()
    instances: tuple[NumberingInstanceBlueprint, ...] = ()


class EmbeddedFaceBlueprint(BlueprintBase):
    asset_id: str
    font_key: str | None = None     # GUID the bytes are obfuscated with; None is a plain font
    subsetted: bool = False


class EmbeddedFontBlueprint(BlueprintBase):
    """A font carried by template. Its faces are stored as assets, byte for byte."""
    name: str
    regular: EmbeddedFaceBlueprint | None = None
    bold: EmbeddedFaceBlueprint | None = None
    italic: EmbeddedFaceBlueprint | None = None
    bold_italic: EmbeddedFaceBlueprint | None = None

    def faces(self) -> tuple[tuple[str, EmbeddedFaceBlueprint], ...]:
        """(kind, face) of the faces present, in the order <w:font> lists them."""

        return tuple(
            (kind, face)
            for kind, face in (
                ("regular", self.regular),
                ("bold", self.bold),
                ("italic", self.italic),
                ("bold_italic", self.bold_italic),
            )
            if face is not None
        )


class DocumentStyleBlueprint(BlueprintBase):
    """What belongs to the document as a whole rather than to one section."""

    background: str | None = None       # page color, hex
    numbering: NumberingBlueprint = NumberingBlueprint()        # only the lists that are used by paragraphs kept
    fonts: tuple[EmbeddedFontBlueprint, ...] = ()