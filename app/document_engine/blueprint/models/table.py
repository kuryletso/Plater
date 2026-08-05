from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.blueprint.models.margins import MarginsBlueprint
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphStyleBlueprint

from app.document_engine.enums.enums import (
    TableCellShading,
    VerticalAlignment,
    TableWidthType,
    TableBorderStyleEnum
)

if TYPE_CHECKING:
    from app.document_engine.blueprint.models.unions import (
        BlueprintBlock,
        BlueprintRow,
        BlueprintCell,
    )


class CellStyleBlueprint(BlueprintBase):
    shading: TableCellShading
    shading_fill: str
    margins: MarginsBlueprint
    grid_span: int
    v_alignment: VerticalAlignment
    border_top: TableBorderBlueprint | None = None
    border_left: TableBorderBlueprint | None = None
    border_bottom: TableBorderBlueprint | None = None
    border_right: TableBorderBlueprint | None = None


class RowStyleBlueprint(BlueprintBase):
    height: int
    header: bool


class TableWidthBlueprint(BlueprintBase):
    value: int | None
    type: TableWidthType


class TableBorderBlueprint(BlueprintBase):
    style: TableBorderStyleEnum
    size: int
    color: str


class TableStyleBlueprint(BlueprintBase):
    width: TableWidthBlueprint
    autofit: bool
    border_top: TableBorderBlueprint
    border_left: TableBorderBlueprint
    border_bottom: TableBorderBlueprint
    border_right: TableBorderBlueprint
    border_inside_v: TableBorderBlueprint
    border_inside_h: TableBorderBlueprint
    margins: MarginsBlueprint
    column_widths: tuple[int, ...] = ()


class CellBlueprint(BlueprintBase):
    type: Literal["cell"] = "cell"
    blocks: tuple[BlueprintBlock, ...]
    style: CellStyleBlueprint


class CellPlaceholder(BlueprintBase):
    type: Literal["placeholder_cell"] = "placeholder_cell"
    key: str
    language: str
    cell_style: CellStyleBlueprint
    text_style: TextStyleBlueprint
    para_style: ParagraphStyleBlueprint


class RowBlueprint(BlueprintBase):
    type: Literal["row"] = "row"
    cells: tuple[BlueprintCell, ...]
    style: RowStyleBlueprint


class RowPlaceholder(BlueprintBase):
    type: Literal["placeholder_row"] = "placeholder_row"
    cells: tuple[BlueprintCell, ...]
    style: RowStyleBlueprint


class TableBlueprint(BlueprintBase):
    type: Literal["table"] = "table"
    rows: tuple[BlueprintRow, ...]
    style: TableStyleBlueprint


class TablePlaceholder(BlueprintBase):
    type: Literal["placeholder_table"] = "placeholder_table"
    key: str = "invoice_table"
    language: str
    text_style: TextStyleBlueprint
    style: TableStyleBlueprint