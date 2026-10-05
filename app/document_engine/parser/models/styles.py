from __future__ import annotations

from typing import Optional
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RunStyle:
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    color: Optional[str] = None
    strike: Optional[bool] = None
    small_caps: Optional[bool] = None
    script: Optional[str] = None       # ST_VerticalAlignRun
    highlight: Optional[str] = None     # ST_HighlightColor; "none" is kept as it switches the inherited one off


@dataclass(slots=True, frozen=True)
class ParagraphBorderStyle:
    style: Optional[str] = None     # ST_Border; 'nil' and 'none' are kept
    size: Optional[int] = None      # eights of a point
    space: Optional[int] = None     # points between the border and the text
    color: Optional[str] = None


@dataclass(slots=True, frozen=True)
class ParagraphStyle:
    alignment: Optional[str] = None
    spacing_before: Optional[int] = None
    spacing_after: Optional[int] = None
    indent_left: Optional[int] = None
    indent_right: Optional[int] = None
    indent_first_line: Optional[int] = None     # negative is a hanging indent
    keep_next: Optional[bool] = None
    line_spacing: Optional[int] = None
    line_rule: Optional[str] = None
    page_break_before: Optional[bool] = None
    border_top: Optional[ParagraphBorderStyle] = None
    border_left: Optional[ParagraphBorderStyle] = None
    border_bottom: Optional[ParagraphBorderStyle] = None
    border_right: Optional[ParagraphBorderStyle] = None
    border_between: Optional[ParagraphBorderStyle] = None
    num_id: Optional[int] = None        # <w:numPr>; 0 switches off numbering from the style
    num_level: Optional[int] = None


@dataclass(slots=True, frozen=True)
class Margins:
    top: Optional[int] = None
    bottom: Optional[int] = None
    left: Optional[int] = None
    right: Optional[int] = None


@dataclass(slots=True, frozen=True)
class TableCellStyle:
    shading: Optional[str] = None
    shading_fill: Optional[str] = None
    margins: Optional[Margins] = None
    grid_span: Optional[int] = None
    v_alignment: Optional[str] = None
    v_merge: Optional[str] = None
    border_top: Optional[TableBorderStyle] = None
    border_left: Optional[TableBorderStyle] = None
    border_bottom: Optional[TableBorderStyle] = None
    border_right: Optional[TableBorderStyle] = None


@dataclass(slots=True, frozen=True)
class TableRowStyle:
    height: Optional[int] = None
    header: Optional[bool] = None


@dataclass(slots=True, frozen=True)
class TableBorderStyle:
    style: Optional[str] = None
    size: Optional[int] = None
    color: Optional[str] = None


@dataclass(slots=True, frozen=True)
class TableStyle:
    width: Optional[int] = None
    width_type: Optional[str] = None
    autofit: Optional[bool] = None
    border_top: Optional[TableBorderStyle] = None
    border_left: Optional[TableBorderStyle] = None
    border_bottom: Optional[TableBorderStyle] = None
    border_right: Optional[TableBorderStyle] = None
    border_inside_v: Optional[TableBorderStyle] = None
    border_inside_h: Optional[TableBorderStyle] = None
    margins: Optional[Margins] = None
    column_widths: Optional[tuple[int, ...]] = None
    alignment: Optional[str] = None


@dataclass(slots=True, frozen=True)
class ColumnWidth:
    width: Optional[int] = None     # twips
    space: Optional[int] = None     # twips after the column


@dataclass(slots=True, frozen=True)
class SectionColumns:
    count: Optional[int] = None
    space: Optional[int] = None     # twips between equal columns
    equal_width: Optional[bool] = None
    separator: Optional[bool] = None        # line between the columns
    widths: tuple[ColumnWidth, ...] = ()


@dataclass(slots=True, frozen=True)
class SectionStyle:
    section_type: Optional[str] = None
    page_width: Optional[int] = None
    page_height: Optional[int] = None
    orientation: Optional[str] = None
    margin_header: Optional[int] = None
    margin_footer: Optional[int] = None
    margins: Optional[Margins] = None
    title_page: Optional[bool] = None
    columns: Optional[SectionColumns] = None
    

@dataclass(slots=True, frozen=True)
class StyleNode:
    style_id: str
    style_type: str
    is_default: bool = False
    name: Optional[str] = None
    based_on: Optional[str] = None
    run_style: Optional[RunStyle] = None
    paragraph_style: Optional[ParagraphStyle] = None
    table_style: Optional[TableStyle] = None
    row_style: Optional[TableRowStyle] = None
    cell_style: Optional[TableCellStyle] = None


@dataclass(slots=True, frozen=True)
class NumberingLevel:
    """One level of a list definition, <w:lvl>."""
    level: int
    start: Optional[int] = None
    format: Optional[str] = None        # ST_NumberFormat: decimal, bullet, lowerRoman etc.
    text: Optional[str] = None      # lvlText: "%1." or the bullet character
    alignment: Optional[str] = None     # lvlJc
    suffix: Optional[str] = None        # ST_LevelSuffix: tab, space, nothing
    indent_left: Optional[int] = None
    indent_first_line: Optional[int] = None     # negative is a hanging indent
    style: RunStyle = RunStyle()        # the number's own formatting, over the paragraph mark


@dataclass(slots=True, frozen=True)
class NumberingDefinition:
    """<w:abstractNum>: the levels a list is drawn with."""
    definition_id: int
    levels: tuple[NumberingLevel, ...] = ()


@dataclass(slots=True, frozen=True)
class NumberingInstance:
    """<w:num>: what a paragraph's numId names."""
    num_id: int
    definition_id: int
    start_overrides: tuple[tuple[int, int], ...] = ()       # (level, start)


@dataclass(slots=True, frozen=True)
class Numbering:
    definitions: tuple[NumberingDefinition, ...] = ()
    instances: tuple[NumberingInstance, ...] = ()

    def level(self, num_id: int, level: int) -> NumberingLevel | None:
        instance = next((i for i in self.instances if i.num_id == num_id), None)
        if instance is None:
            return None

        definition = next((d for d in self.definitions if d.definition_id == instance.definition_id), None)
        if definition is None:
            return None

        return next((lvl for lvl in definition.levels if lvl.level == level), None)

    def only(self, num_ids: set[int]) -> Numbering:
        """The instances that paragraphs use, and the definitions behind them."""

        instances = tuple(i for i in self.instances if i.num_id in num_ids)
        used = {i.definition_id for i in instances}

        return Numbering(
            definitions=tuple(d for d in self.definitions if d.definition_id in used),
            instances=instances,
        ) 


@dataclass(slots=True, frozen=True)
class EmbeddedFace:
    """The face of a font the document carries with it, <w:embedRegular> and its kin."""
    asset_id: str
    font_key: Optional[str] = None      # GUID the bytes are obfuscated with
    subsetted: Optional[bool] = None


@dataclass(slots=True, frozen=True)
class EmbeddedFont:
    name: str
    regular: Optional[EmbeddedFace] = None
    bold: Optional[EmbeddedFace] = None
    italic: Optional[EmbeddedFace] = None
    bold_italic: Optional[EmbeddedFace] = None


@dataclass(slots=True, frozen=True)
class DocumentStyle:
    """What belong to the document as a whole rather than to one section."""
    background: Optional[str] = None        # page color: ST_HexColor or "auto"
    numbering: Numbering = Numbering()      # only the lists paragraphs use
    fonts: tuple[EmbeddedFont, ...] = ()