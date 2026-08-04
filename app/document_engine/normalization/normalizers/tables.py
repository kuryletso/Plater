from typing import cast

from app.document_engine.normalization.models.blocks import (
    NormalizedTable,
    NormalizedTableStyle,
    NormalizedRow,
    NormalizedRowStyle,
    NormalizedCell,
    NormalizedCellStyle,
    NormalizedTableWidth,
    NormalizedTableBorder,
)
from app.document_engine.normalization.normalizers.paragraphs import normalize_paragraph
from app.document_engine.normalization.errors import NormalizationFormatError
from app.document_engine.normalization.normalizers.shared import normalize_margins
from app.document_engine.normalization.style_defaults import (
    DEFAULT_TABLE_WIDTH,
    DEFAULT_TABLE_BORDER,
    DEFAULT_TABLE_STYLE,
    DEFAULT_ROW_STYLE,
    DEFAULT_CELL_STYLE,
    DEFAULT_CELL_MARGINS,
    DEFAULT_TABLE_MARGINS,
)

from app.document_engine.parser.models.blocks import ParagraphNode, TableNode, TableRowStyle, TableCellStyle
from app.document_engine.parser.models.styles import TableBorderStyle

from app.document_engine.enums.enums import TableWidthType, TableBorderStyleEnum, TableCellShading, VerticalAlignment
from app.document_engine.utils.overlay_dataclass import overlay_dataclass_strict

from app.core.diagnostics import DiagnosticCollector
from app.core.errors import Layer


def normalize_table_width(
        value: int | None,
        type: str | None,
        diagnostics: DiagnosticCollector,
) -> NormalizedTableWidth:
    
    if type is None:
        return DEFAULT_TABLE_WIDTH
    
    if type != "auto" and value is None:
        diagnostics.warn(
            Layer.NORMALIZATION,
            "missing_table_width",
            f"Table width value missing for type '{type}'; using the default width.",
        )
        return DEFAULT_TABLE_WIDTH
    
    try:
        return NormalizedTableWidth(
            value=value,
            type=TableWidthType(type),
        )
    except ValueError:
        diagnostics.warn(
            Layer.NORMALIZATION,
            "invalid_table_width",
            f"Invalid table width attribute ({type=}, {value=}); using the default width.",
        )
        return DEFAULT_TABLE_WIDTH


def normalize_table_border(border: TableBorderStyle | None) -> NormalizedTableBorder:
    if border is None:
        return DEFAULT_TABLE_BORDER

    if isinstance(border.size, int) and border.size < 0:
        raise NormalizationFormatError(
            f"Table border size can't be negative, got {border.size=}."
        )

    try:
        style = TableBorderStyleEnum(border.style) \
            if border.style is not None \
            else None
    except ValueError as e:
        raise NormalizationFormatError(
            f"Invalid border style: '{border.style}'."
        ) from e

    parsed_style = NormalizedTableBorder(
        # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
        style=cast(TableBorderStyleEnum, style),
        size=cast(int, border.size),
        color=cast(str, border.color),
    )

    return overlay_dataclass_strict(
        DEFAULT_TABLE_BORDER,
        parsed_style,
    )
    

def normalize_row_style(row_style: TableRowStyle | None) -> NormalizedRowStyle:
    if row_style is None:
        return DEFAULT_ROW_STYLE
    
    if isinstance(row_style.height, int) and row_style.height < 1:
        raise NormalizationFormatError(
            f"Table row height must be at least 1, got {row_style.height=}."
        )

    parsed_style = NormalizedRowStyle(
        # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
        height=cast(int, row_style.height),
        header=cast(bool, row_style.header),
    )

    return overlay_dataclass_strict(
        DEFAULT_ROW_STYLE,
        parsed_style,
    )


def normalize_cell_border(border: TableBorderStyle | None) -> NormalizedTableBorder | None:
    """Unlike table borders, an unset cell border means 'inherit', not 'None'."""

    return normalize_table_border(border) if border is not None else None


def normalize_cell_style(cell_style: TableCellStyle | None) -> NormalizedCellStyle:
    if cell_style is None:
        return DEFAULT_CELL_STYLE
    
    if isinstance(cell_style.grid_span, int) and cell_style.grid_span < 1:
        raise NormalizationFormatError(
            f"Table cell span must be at least 1, got {cell_style.grid_span=}"
        )

    try:
        shading = TableCellShading(cell_style.shading) \
            if cell_style.shading is not None \
            else None
    except ValueError as e:
        raise NormalizationFormatError(
            f"Invalid cell shading: '{cell_style.shading}'."
        ) from e
    
    try:
        v_alignment = VerticalAlignment(cell_style.v_alignment) \
            if cell_style.v_alignment is not None \
            else None
    except ValueError as e:
        raise NormalizationFormatError(
            f"Invalid cell v_alignment: '{cell_style.v_alignment}'."
        ) from e

    parsed_style = NormalizedCellStyle(
        shading=cast(TableCellShading, shading),
        shading_fill=cast(str, cell_style.shading_fill),
        margins=normalize_margins(
            margins=cell_style.margins,
            default=DEFAULT_CELL_MARGINS,
        ),
        grid_span=cast(int, cell_style.grid_span),
        v_alignment=cast(VerticalAlignment, v_alignment),
        border_top=normalize_cell_border(cell_style.border_top),
        border_left=normalize_cell_border(cell_style.border_left),
        border_bottom=normalize_cell_border(cell_style.border_bottom),
        border_right=normalize_cell_border(cell_style.border_right),
    )
    
    return overlay_dataclass_strict(
        DEFAULT_CELL_STYLE,
        parsed_style,
    )


def normalize_table(
        table: TableNode,
        diagnostics: DiagnosticCollector,
) -> NormalizedTable:

    parsed_style = NormalizedTableStyle(
        # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
        width=normalize_table_width(
            table.style.width,
            table.style.width_type,
            diagnostics,
        ),
        autofit=cast(bool, table.style.autofit),
        border_top=normalize_table_border(table.style.border_top),
        border_left=normalize_table_border(table.style.border_left),
        border_bottom=normalize_table_border(table.style.border_bottom),
        border_right=normalize_table_border(table.style.border_right),
        border_inside_v=normalize_table_border(table.style.border_inside_v),
        border_inside_h=normalize_table_border(table.style.border_inside_h),
        margins=normalize_margins(
            margins=table.style.margins,
            default=DEFAULT_TABLE_MARGINS,
        ),
        column_width=cast(tuple[int, ...], table.style.column_widths),       # overlay_dataclass_strict fills the () default
    )

    normalized_style = overlay_dataclass_strict(
        DEFAULT_TABLE_STYLE,
        parsed_style,
    )

    normalized_rows = []
    for row in table.rows:
        normalized_cells = []

        for cell in row.cells:
            normalized_blocks = []

            for block in cell.blocks:
                if isinstance(block, ParagraphNode):
                    normalized_blocks.append(
                        normalize_paragraph(block),
                    )

                elif isinstance(block, TableNode):
                    normalized_blocks.append(
                        normalize_table(block, diagnostics),
                    )

            normalized_cells.append(
                NormalizedCell(
                    blocks=tuple(normalized_blocks),
                    style=normalize_cell_style(cell.style),
                )
            )

        normalized_rows.append(
            NormalizedRow(
                cells=tuple(normalized_cells),
                style=normalize_row_style(row.style)
            )
        )

    return NormalizedTable(
        rows=tuple(normalized_rows),
        style=normalized_style,
    )