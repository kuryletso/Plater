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


@dataclass(slots=True, frozen=True)
class ParagraphStyle:
    alignment: Optional[str] = None
    spacing_before: Optional[int] = None
    spacing_after: Optional[int] = None
    indent_left: Optional[int] = None
    indent_right: Optional[int] = None
    keep_next: Optional[bool] = None


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
    border_bottom: Optional[TableBorderStyle] = None
    border_left: Optional[TableBorderStyle] = None
    border_right: Optional[TableBorderStyle] = None
    border_inside_v: Optional[TableBorderStyle] = None
    border_inside_h: Optional[TableBorderStyle] = None
    margins: Optional[Margins] = None
    column_widths: Optional[tuple[int, ...]] = None


@dataclass(slots=True, frozen=True)
class SectionStyle:
    section_type: Optional[str] = None
    page_width: Optional[int] = None
    page_height: Optional[int] = None
    orientation: Optional[str] = None
    margin_header: Optional[int] = None
    margin_footer: Optional[int] = None
    margins: Optional[Margins] = None
    

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