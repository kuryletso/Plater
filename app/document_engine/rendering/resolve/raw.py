from __future__ import annotations

from app.document_engine.blueprint.models.paragraph import ParagraphStyleBlueprint
from app.document_engine.rendering.context import InvoiceLineRow, InvoiceTableData
from app.document_engine.rendering.resolve.invoice_table import (
    COLUMNS, SUBTOTAL_LABEL, TOTAL_TAX_LABEL, TOTAL_LABEL,
)
from app.document_engine.enums.enums import ParagraphAlignment


RAW_SINGLE_ROW = InvoiceTableData(
    rows=(InvoiceLineRow(values={}),),
    show_tax=True,
    subtotal={},
    total_tax={},
    total={},
    labels={},
)


def placeholder_syntax(key: str) -> str:
    return f"{{{{ {key} }}}}"


def raw_table_data(language: str) -> InvoiceTableData:
    """A single line of column keys, so a system table shows what feeds each cell."""

    keys = { column: {language: placeholder_syntax(column)} for column in COLUMNS }
    labels = dict(keys) | {
        label: {language: placeholder_syntax(label)}
        for label in (SUBTOTAL_LABEL, TOTAL_TAX_LABEL, TOTAL_LABEL)
    }

    return InvoiceTableData(
        rows=(InvoiceLineRow(values=keys),),
        show_tax=True,
        subtotal={language: placeholder_syntax(SUBTOTAL_LABEL)},
        total_tax={language: placeholder_syntax(TOTAL_TAX_LABEL)},
        total={language: placeholder_syntax(TOTAL_LABEL)},
        labels=labels,
    )


def raw_paragtaph_style() -> ParagraphStyleBlueprint:
    return ParagraphStyleBlueprint(
        alignment=ParagraphAlignment.LEFT,
        spacing_before=0,
        spacing_after=0,
        indent_left=0,
        indent_right=0,
        keep_next=False,
    )