from __future__ import annotations

from app.document_engine.enums.enums import (
    ParagraphAlignment, VerticalAlignment, TableCellShading,
)
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphStyleBlueprint
from app.document_engine.blueprint.models.margins import MarginsBlueprint
from app.document_engine.blueprint.models.table import (
    TablePlaceholder,
    RowStyleBlueprint, CellStyleBlueprint,
)
from app.document_engine.rendering.context import InvoiceTableData, InvoiceLineRow
from app.document_engine.rendering.resolve.models import (
    ResolvedTable, ResolvedRow, ResolvedCell,
    ResolvedParagraph, ResolvedTextRun,
)
from app.document_engine.enums.enums import TableWidthType


NUMBER, DESCRIPTION, UNIT = "invl_n", "invl_desc", "invl_unit"
QUANTITY, PRICE, TAX, TOTAL = "invl_qnty", "invl_price", "invl_tax", "invl_total"

COLUMNS = (NUMBER, DESCRIPTION, UNIT, QUANTITY, PRICE, TAX, TOTAL)
RIGHT_ALIGNED = {QUANTITY, PRICE, TAX, TOTAL}
COLUMN_WEIGHTS = {
    NUMBER: 4, DESCRIPTION: 34, UNIT: 9,
    QUANTITY: 9, PRICE: 13, TAX: 12, TOTAL: 15,
}

FALLBACK_WIDTH = 9026       # A4, up to 1" margins

SUBTOTAL_LABEL, TOTAL_TAX_LABEL, TOTAL_LABEL = "subtotal", "total_tax", "total"

DEFAULT_FONT = "Arial"        # TODO: source from document default
DEFAULT_SIZE = 22       # half-points

_MARGINS = MarginsBlueprint(top=50, bottom=50, left=100, right=100)


def build_invoice_table(
    placeholder: TablePlaceholder,
    data: InvoiceTableData,
) -> ResolvedTable:
    
    lang = placeholder.language
    columns = [c for c in COLUMNS if c != TAX or data.show_tax]
    ncols = len(columns)

    rows: list[ResolvedRow] = []

    rows.append(ResolvedRow(
        cells=tuple(
            _cell(_val(data.labels, col, lang), base=placeholder.text_style, bold=True, alignment=ParagraphAlignment.CENTER)
            for col in columns
        ),
        style=RowStyleBlueprint(height=0, header=True),
    ))

    for line in data.rows:
        rows.append(ResolvedRow(
            cells=tuple(
                _cell(_val(line.values, col, lang), base=placeholder.text_style, bold=False, alignment=_data_align(col))
                for col in columns
            ),
            style=RowStyleBlueprint(height=0, header=False),
        ))

    if data.show_tax and data.total_tax is not None:
        rows.append(_summary(data.labels, SUBTOTAL_LABEL, data.subtotal, lang, ncols, base=placeholder.text_style, bold=False))
        rows.append(_summary(data.labels, TOTAL_TAX_LABEL, data.total_tax, lang, ncols, base=placeholder.text_style, bold=False))
    rows.append(_summary(data.labels, TOTAL_LABEL, data.total, lang, ncols, base=placeholder.text_style, bold=True))

    widths = _column_width(placeholder.style, columns)

    return ResolvedTable(
        rows=tuple(rows),
        style=placeholder.style.model_copy(
            update={
                "column_widths": widths,
                "autofit": False,
            }
        ),
    )


def _text(bold: bool) -> TextStyleBlueprint:
    return TextStyleBlueprint(
        bold=bold,
        italic=False,
        underline=False,
        font_name=DEFAULT_FONT,
        font_size=DEFAULT_SIZE,
        color="000000",
    )


def _para(alignment: ParagraphAlignment) -> ParagraphStyleBlueprint:
    return ParagraphStyleBlueprint(
        alignment=alignment,
        spacing_before=0,
        spacing_after=0,
        indent_left=0,
        indent_right=0,
        keep_next=False,
    )


def _cell_style(grid_span: int = 1) -> CellStyleBlueprint:
    return CellStyleBlueprint(
        shading=TableCellShading.CLEAR,
        shading_fill="auto",
        margins=_MARGINS,
        grid_span=grid_span,
        v_alignment=VerticalAlignment.CENTER,
    )


def _cell(
    text: str,
    base: TextStyleBlueprint,
    bold: bool,
    alignment: ParagraphAlignment,
    grid_span: int = 1,
) -> ResolvedCell:
    
    style = base.model_copy(update={"bold": bold})
    para = ResolvedParagraph(
        runs=(ResolvedTextRun(text=text, style=style),),
        style=_para(alignment),
    )
    return ResolvedCell(
        blocks=(para,),
        style=_cell_style(grid_span),
    )


def _val(mapping, key: str, lang: str) -> str:
    values = mapping.get(key)
    return (values.get(lang) or "") if values is not None else ""


def _data_align(col: str) -> ParagraphAlignment:
    if col in RIGHT_ALIGNED:
        return ParagraphAlignment.RIGHT
    if col == NUMBER:
        return ParagraphAlignment.CENTER
    return ParagraphAlignment.LEFT


def _summary(labels, label_key, amount, lang, ncols, base: TextStyleBlueprint, bold) -> ResolvedRow:
    return ResolvedRow(
        cells=(
            _cell(_val(labels, label_key, lang), base=base, bold=bold, alignment=ParagraphAlignment.RIGHT, grid_span=ncols-1),
            _cell((amount.get(lang) or ""), base=base, bold=bold, alignment=ParagraphAlignment.RIGHT),
        ),
        style=RowStyleBlueprint(height=0, header=False),
    )


def _column_width(style, columns: list[str]) -> tuple[int, ...]:
    total = (
        style.width.value
        if style.width.type is TableWidthType.DXA and style.width.value
        else FALLBACK_WIDTH
    )
    weights = [ COLUMN_WEIGHTS[column] for column in columns ]
    scale = sum(weights)

    widths = [ total * weight // scale for weight in weights ]
    widths[-1] += total - sum(widths)

    return tuple(widths)