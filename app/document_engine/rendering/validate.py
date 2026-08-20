from __future__ import annotations

from app.core.diagnostics import DiagnosticCollector, Diagnostic
from app.core.errors import Layer, Severity

from app.document_engine.blueprint.models.template import TemplateBlueprint
from app.document_engine.blueprint.models.section import SectionBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.table import (
    TableBlueprint, TablePlaceholder,
    RowBlueprint, RowPlaceholder,
    CellBlueprint, CellPlaceholder,
)
from app.document_engine.blueprint.models.segment import (
    PlaceholderSegment, JoinedPlaceholderSegment, GroupedPlaceholderSegment,
)

from app.document_engine.rendering.context import RenderContext


def blueprint_uses_table(
    blueprint: TemplateBlueprint,
) -> bool:
    
    return any(_section_uses_table(s) for s in blueprint.sections)


def column_languages(
        blueprint: TemplateBlueprint,
        key: str,
) -> set[str]:
    """Languages a given table column is actually rendered in.
    Unsuffixed placeholders were resolved to the template's default language
    at ingestion, so the result is always concrete codes.
    """

    _, columns, _, _ = _collect_usage(blueprint)
    return { language for column_key, language in columns if column_key == key }


def _section_uses_table(
    section: SectionBlueprint,
) -> bool:
    
    if _blocks_use_table(section.blocks):
        return True
    for group in (section.headers, section.footers):
        for hf in (group.default, group.first, group.even):
            if hf is not None and _blocks_use_table(hf.blocks):
                return True
            
    return False


def _blocks_use_table(
    blocks,
) -> bool:
    
    for block in blocks:
        if isinstance(block, TablePlaceholder):
            return True
        
        if isinstance(block, TableBlueprint):
            for row in block.rows:
                if isinstance(row, RowPlaceholder):
                    return True
                for cell in row.cells:
                    if isinstance(cell, CellBlueprint) and _blocks_use_table(cell.blocks):
                        return True
                    
    return False


def validate_context(
    blueprint: TemplateBlueprint,
    context: RenderContext,
    diag: DiagnosticCollector,
) -> bool:
    """Record and ERROR diagnostic for every missing required value; return validity."""

    scalars, columns, table_langs, uses_table = _collect_usage(blueprint)
    required = {k: d.required for k,d in blueprint.placeholders.items()}

    def error(
        code: str,
        message: str,
        **context
    ) -> None:
        
        diag.record(Diagnostic(
            Layer.RENDER,
            Severity.ERROR,
            code,
            message,
            context or None,
        ))

    # check required scalar placeholders
    for key, lang in scalars:
        if required.get(key, True) \
        and _lookup(context.scalars, key, lang) is None:
            error(
                "missing_required_value",
                f"Required placeholder '{key}' ({lang}) has no value.",
                key=key, language=lang,
            )

    # check table placeholder values
    if uses_table:
        if context.table is None:
            error(
                "missing_table_data",
                "Template uses a table placeholder but no table data was provided.",
            )
        else:
            if not context.table.rows:
                diag.warn(
                    Layer.RENDER,
                    "empty_table",
                    "Table data has no rows; the table will render empty.",
                )

            for key, lang in columns:
                if any(
                    _lookup(row.values, key, lang) is None \
                    for row in context.table.rows
                ):
                    error(
                        "missing_column_value",
                        f"Column '{key}' ({lang}) is missing in one or more rows.",
                        key=key, language=lang,
                    )

            for lang in table_langs:
                _validate_totals(context.table, lang, error)

    return not diag.has_errors


def _lookup(
    mapping,
    key,
    language,
):
    values = mapping.get(key)
    return values.get(language) if values is not None else None


def _validate_totals(
    table,
    lang,
    error,
) -> None:
    
    if table.subtotal.get(lang) is None:
        error(
            "missing_total",
            f"invoice_table subtotal missing for '{lang}'.",
            language=lang,
        )
    if table.total.get(lang) is None:
        error(
            "missing_total",
            f"invoice_table total missing for '{lang}'.",
            language=lang,
        )
    if table.show_tax and (table.total_tax is None or table.total_tax.get(lang) is None):
        error(
            "missing_total",
            f"invoice_table total tax missing for '{lang}'.",
            language=lang,
        )


def _collect_usage(
    blueprint: TemplateBlueprint,
):
    scalars: set[tuple[str, str]] = set()
    columns: set[tuple[str, str]] = set()
    table_langs: set[str] = set()
    uses_table = False

    def visit_segment(seg) -> None:
        if isinstance(seg, PlaceholderSegment):
            scalars.add((seg.key, seg.language))
        elif isinstance(seg, JoinedPlaceholderSegment):
            for item in seg.items:
                if isinstance(item, PlaceholderSegment):
                    scalars.add((item.key, item.language))
        elif isinstance(seg, GroupedPlaceholderSegment):
            for group in seg.items:
                for item in group:
                    if isinstance(item, PlaceholderSegment):
                        scalars.add((item.key, item.language))

    def visit_blocks(blocks) -> None:
        nonlocal uses_table
        for block in blocks:
            if isinstance(block, ParagraphBlueprint):
                for seg in block.segments:
                    visit_segment(seg)
            elif isinstance(block, TablePlaceholder):
                uses_table = True
                table_langs.add(block.language)
            elif isinstance(block, TableBlueprint):
                for row in block.rows:
                    cells = row.cells
                    if isinstance(row, RowPlaceholder):
                        uses_table = True
                    for cell in cells:
                        if isinstance(cell, CellPlaceholder):
                            columns.add((cell.key, cell.language))
                        elif isinstance(cell, CellBlueprint):
                            visit_blocks(cell.blocks)

    for section in blueprint.sections:
        visit_blocks(section.blocks)
        for group in (section.headers, section.footers):
            for hf in (group.default, group.first, group.even):
                if hf is not None:
                    visit_blocks(hf.blocks)

    return scalars, columns, table_langs, uses_table