from __future__ import annotations

from dataclasses import dataclass

from app.document_engine.normalization.models.inlines import NormalizedInlineNode
from app.document_engine.normalization.models.shared import NormalizedMargins

from app.document_engine.enums.enums import ParagraphAlignment, TableCellShading, VerticalAlignment, TableBorderStyleEnum, TableWidthType


@dataclass(slots=True, frozen=True)
class NormalizedParagraphStyle:
    alignment: ParagraphAlignment
    spacing_before: int         # twips
    spacing_after: int          # twips
    indent_left: int            # twips
    indent_right: int           # twips
    keep_next: bool


@dataclass(slots=True, frozen=True)
class NormalizedParagraph:
    inlines: tuple[NormalizedInlineNode, ...]
    style: NormalizedParagraphStyle


@dataclass(slots=True, frozen=True)
class NormalizedCellStyle:
    shading: TableCellShading
    shading_fill: str
    margins: NormalizedMargins
    grid_span: int
    v_alignment: VerticalAlignment
    border_top: NormalizedTableBorder | None
    border_left: NormalizedTableBorder | None
    border_bottom: NormalizedTableBorder | None
    border_right: NormalizedTableBorder | None


@dataclass(slots=True, frozen=True)
class NormalizedRowStyle:
    height: int
    header: bool


@dataclass(slots=True, frozen=True)
class NormalizedTableBorder:
    style: TableBorderStyleEnum
    size: int
    color: str


@dataclass(slots=True, frozen=True)
class NormalizedTableWidth:
    value: int | None
    type: TableWidthType        # dxa / pct / auto


@dataclass(slots=True, frozen=True)
class NormalizedTableStyle:
    width: NormalizedTableWidth
    autofit: bool
    border_top: NormalizedTableBorder
    border_left: NormalizedTableBorder
    border_bottom: NormalizedTableBorder
    border_right: NormalizedTableBorder
    border_inside_v: NormalizedTableBorder
    border_inside_h: NormalizedTableBorder
    margins: NormalizedMargins
    column_width: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class NormalizedCell:
    blocks: tuple[NormalizedBlock, ...]
    style: NormalizedCellStyle


@dataclass(slots=True, frozen=True)
class NormalizedRow:
    cells: tuple[NormalizedCell, ...]
    style: NormalizedRowStyle


@dataclass(slots=True, frozen=True)
class NormalizedTable:
    rows: tuple[NormalizedRow, ...]
    style: NormalizedTableStyle

type NormalizedBlock = NormalizedParagraph | NormalizedTable