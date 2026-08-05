from __future__ import annotations

from typing import cast

from app.core.diagnostics import Layer

from app.document_engine.blueprint.template_builder import TemplateBuilderContext
from app.document_engine.blueprint.builders.margins import margins_bp_from_normalized
from app.document_engine.blueprint.builders.paragraph import paragraph_bp_from_normalized
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.segment import PlaceholderSegment, TextStyleBlueprint
from app.document_engine.blueprint.models.table import (
    TableBlueprint,
    TablePlaceholder,
    RowBlueprint,
    RowPlaceholder,
    CellBlueprint,
    CellPlaceholder,
    TableStyleBlueprint,
    RowStyleBlueprint,
    CellStyleBlueprint,
    TableWidthBlueprint,
    TableBorderBlueprint,
)
from app.document_engine.blueprint.models.margins import MarginsBlueprint
from app.document_engine.blueprint.models.segment import TextSegment
from app.document_engine.blueprint.errors import BlueprintBuilderError, PlaceholderSyntaxError

from app.document_engine.normalization.models.blocks import (
    NormalizedTable,
    NormalizedRow,
    NormalizedCell,
    NormalizedTableStyle,
    NormalizedRowStyle,
    NormalizedCellStyle,
    NormalizedTableWidth,
    NormalizedTableBorder,
    NormalizedParagraph,
)
from app.document_engine.enums.enums import PlaceholderType, TableBorderStyleEnum, TableWidthType


DEFAULT_STANDALONE_TABLE_BORDER = TableBorderBlueprint(
    style=TableBorderStyleEnum.SINGLE,
    size=4,
    color="000000",
)

DEFAULT_STANDALONE_TABLE_STYLE = TableStyleBlueprint(
    width=TableWidthBlueprint(value=0, type=TableWidthType.AUTO),
    autofit=True,
    border_top=DEFAULT_STANDALONE_TABLE_BORDER,
    border_left=DEFAULT_STANDALONE_TABLE_BORDER,
    border_bottom=DEFAULT_STANDALONE_TABLE_BORDER,
    border_right=DEFAULT_STANDALONE_TABLE_BORDER,
    border_inside_v=DEFAULT_STANDALONE_TABLE_BORDER,
    border_inside_h=DEFAULT_STANDALONE_TABLE_BORDER,
    margins=MarginsBlueprint(top=0, left=0, bottom=0, right=0),
    column_widths=(),
)


def table_border_bp_from_normalized(
    normalized: NormalizedTableBorder,
) -> TableBorderBlueprint:
    
    return TableBorderBlueprint(
        style=normalized.style,
        size=normalized.size,
        color=normalized.color,
    )


def table_width_bp_from_normalized(
    normalized: NormalizedTableWidth,
) -> TableWidthBlueprint:
    
    return TableWidthBlueprint(
        value=normalized.value,
        type=normalized.type,
    )


def cell_style_bp_from_normalized(
    normalized: NormalizedCellStyle,
) -> CellStyleBlueprint:
    
    def border(value):
        return table_border_bp_from_normalized(value) if value is not None else None
    
    return CellStyleBlueprint(
        shading=normalized.shading,
        shading_fill=normalized.shading_fill,
        margins=margins_bp_from_normalized(normalized.margins),
        grid_span=normalized.grid_span,
        v_alignment=normalized.v_alignment,
        border_top=border(normalized.border_top),
        border_left=border(normalized.border_left),
        border_bottom=border(normalized.border_bottom),
        border_right=border(normalized.border_right),
    )


def cell_bp_from_normalized(
    normalized: NormalizedCell,
    context: TemplateBuilderContext,
) -> CellBlueprint:
    
    style = cell_style_bp_from_normalized(normalized.style)

    blocks = []
    for block in normalized.blocks:
        if isinstance(block, NormalizedParagraph):
            blocks.append(
                paragraph_bp_from_normalized(
                    block,
                    context,
                )
            )

        elif isinstance(block, NormalizedTable):
            blocks.append(
                table_bp_from_normalized(
                    block,
                    context,
                )
            )

    return CellBlueprint(
        blocks=tuple(blocks),
        style=style,
    )


def row_style_from_normalized(
    normalized: NormalizedRowStyle,
) -> RowStyleBlueprint:
    
    return RowStyleBlueprint(
        height=normalized.height,
        header=normalized.header,
    )


def row_bp_from_normalized(
    normalized: NormalizedRow,
    context: TemplateBuilderContext,
) -> RowBlueprint:
    
    style = row_style_from_normalized(normalized.style)

    cells = []
    for cell in normalized.cells:
        cells.append(
            cell_bp_from_normalized(
                cell,
                context,
            )
        )

    return RowBlueprint(
        cells=tuple(cells),
        style=style,
    )


def table_style_bp_from_normalized(
    normalized: NormalizedTableStyle,
) -> TableStyleBlueprint:
    
    return TableStyleBlueprint(
        width=table_width_bp_from_normalized(normalized.width),
        autofit=normalized.autofit,
        border_top=table_border_bp_from_normalized(normalized.border_top),
        border_left=table_border_bp_from_normalized(normalized.border_left),
        border_bottom=table_border_bp_from_normalized(normalized.border_bottom),
        border_right=table_border_bp_from_normalized(normalized.border_right),
        border_inside_v=table_border_bp_from_normalized(normalized.border_inside_v),
        border_inside_h=table_border_bp_from_normalized(normalized.border_inside_h),
        margins=margins_bp_from_normalized(normalized.margins),
        column_widths=normalized.column_width,
    )


def _promote_placeholder_rows(
    table: TableBlueprint,
) -> TableBlueprint | TablePlaceholder:
     
    new_rows = []
    replace_table = False
    table_language, table_text_style = None, None

    for row in table.rows:

        if replace_table:
            break

        placeholder_cells = {}

        for i, cell in enumerate(row.cells):

            if replace_table:
                break

            if isinstance(cell, CellPlaceholder):
                raise BlueprintBuilderError(
                    "Table's placeholder rows are already promoted."
                )

            else:
                for block in cell.blocks:

                    if replace_table:
                        break

                    if isinstance(block, ParagraphBlueprint):
                        for seg in block.segments:
                            if isinstance(seg, PlaceholderSegment):
                                if seg.ph_type == PlaceholderType.TABLE:
                                    replace_table = True
                                    table_language = seg.language
                                    table_text_style = seg.style
                                    break

                                elif seg.ph_type == PlaceholderType.COLUMN:
                                    
                                    if i in placeholder_cells:
                                        raise PlaceholderSyntaxError(
                                            "Only one invoice line placeholder per cell is supported."
                                        )
                                    
                                    placeholder_cells[i] = CellPlaceholder(
                                        key=seg.key,
                                        language=seg.language,
                                        cell_style=cell.style,
                                        text_style=seg.style,
                                        para_style=block.style,
                                    )

        if placeholder_cells:
            new_cells = [
                cell if i not in placeholder_cells.keys()
                else placeholder_cells[i]
                for i, cell in enumerate(row.cells)
            ]
            new_rows.append(
                RowPlaceholder(
                    cells=tuple(new_cells),
                    style=row.style,
                )
            )
        else:
            new_rows.append(row)

    if replace_table:
        return TablePlaceholder(
            type="placeholder_table",
            language=cast(str, table_language),        # all good here
            text_style=cast(TextStyleBlueprint, table_text_style),    # table_language and table_text_stlye won't be None if replace_table is True
            style=table.style,
        )
    
    else:
        return table.model_copy(update={"rows": tuple(new_rows)})


def table_bp_from_normalized(
    normalized: NormalizedTable,
    context: TemplateBuilderContext,
) -> TableBlueprint | TablePlaceholder:
    
    style = table_style_bp_from_normalized(normalized.style)

    rows = []
    for row in normalized.rows:
        rows.append(
            row_bp_from_normalized(
                row,
                context,
            )
        )

    table = TableBlueprint(
        type="table",
        rows=tuple(rows),
        style=style,
    )

    return _promote_placeholder_rows(table)


def promote_standalone_table(
        paragraph: ParagraphBlueprint,
        context: TemplateBuilderContext,
) -> ParagraphBlueprint | TablePlaceholder:
    """A table placeholder alone in its paragraph becomes a table in its own right.
    
    Inside a table the wrapper supplies the style. Standalone it falls back to a plain bordered default.
    """

    table_segment = next(
        (
            s for s in paragraph.segments
            if isinstance(s, PlaceholderSegment) and s.ph_type is PlaceholderType.TABLE
        ),
        None,
    )
    if table_segment is None:
        return paragraph

    companions = [
        s for s in paragraph.segments
        if s is not table_segment
        and not (isinstance(s, TextSegment) and not s.text.strip())
    ]
    if companions:
        context.diagnostics.warn(
            Layer.BLUEPRINT,
            "table_placeholder_not_alone",
            f"'{table_segment.key}' must be the only content of its paragraph "
            f"to become a table; left as text.",
            key=table_segment.key,
        )
        return paragraph

    return TablePlaceholder(
        type="placeholder_table",
        key=table_segment.key,
        language=table_segment.language,
        text_style=table_segment.style,
        style=DEFAULT_STANDALONE_TABLE_STYLE,
    )