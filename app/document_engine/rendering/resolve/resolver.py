from __future__ import annotations


from app.core.diagnostics import DiagnosticCollector
from app.core.errors import Layer


from app.document_engine.blueprint.models.template import TemplateBlueprint
from app.document_engine.blueprint.models.section import SectionBlueprint
from app.document_engine.blueprint.models.header_footer import (
    HeaderFooterGroupBlueprint, HeaderFooterBlueprint,
)
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.table import (
    TableBlueprint, TablePlaceholder,
    RowBlueprint, RowPlaceholder,
    CellBlueprint, CellPlaceholder,
)
from app.document_engine.blueprint.models.segment import (
    TextSegment, ImageSegment,
    PlaceholderSegment, JoinedPlaceholderSegment, GroupedPlaceholderSegment,
)


from app.document_engine.rendering.context import RenderContext
from app.document_engine.rendering.ports import AssetProvider
from app.document_engine.rendering.errors import PlaceholderError
from app.document_engine.rendering.resolve.models import (
    ResolvedDocument, ResolvedSection, ResolvedParagraph,
    ResolvedTable, ResolvedRow, ResolvedCell, ResolvedBlock,
    ResolvedTextRun, ResolvedImageRun, ResolvedRun,
    ResolvedHeaderFooter, ResolvedHeaderFooterGroup,
)
from app.document_engine.rendering.resolve.invoice_table import build_invoice_table
from app.document_engine.rendering.resolve.raw import placeholder_syntax, raw_table_data, RAW_SINGLE_ROW, raw_paragtaph_style
from app.document_engine.enums.enums import ResolveMode


class DocumentResolver:

    def __init__(
        self,
        context: RenderContext,
        assets: AssetProvider,
        diagnostics: DiagnosticCollector,
        mode: ResolveMode = ResolveMode.VALUES,
    ) -> None:
        
        self._context = context
        self._assets = assets
        self._diag = diagnostics
        self._mode = mode
        self._required: dict[str, bool] = {}


    def resolve(
        self,
        blueprint: TemplateBlueprint,
    ) -> ResolvedDocument:
        
        self._required = {k: d.required for k,d in blueprint.placeholders.items()}
        sections = tuple(self._section(s) for s in blueprint.sections)

        return ResolvedDocument(
            sections=sections,
            config=blueprint.config,
        )
    

    def _section(
        self,
        section: SectionBlueprint,
    ) -> ResolvedSection:
        
        return ResolvedSection(
            blocks=tuple(
                b for b \
                in (self._block(x) for x in section.blocks) \
                if b is not None
            ),
            headers=self._hf_group(section.headers),
            footers=self._hf_group(section.footers),
            style=section.style,
        )
    

    def _hf_group(
        self,
        group: HeaderFooterGroupBlueprint,
    ) -> ResolvedHeaderFooterGroup:
        
        return ResolvedHeaderFooterGroup(
            default=self._hf(group.default),
            first=self._hf(group.first),
            even=self._hf(group.even),
        )
    

    def _hf(
        self,
        hf: HeaderFooterBlueprint | None,
    ) -> ResolvedHeaderFooter | None:
        
        if hf is None:
            return None
        
        return ResolvedHeaderFooter(
            blocks=tuple(
                b for b \
                in (self._block(x) for x in hf.blocks) \
                if b is not None
            ),
        )
    

    def _paragraph(
        self,
        para: ParagraphBlueprint,
    ) -> ResolvedParagraph:
        
        runs: list[ResolvedRun] = []
        for seg in para.segments:
            runs.extend(self._segment_runs(seg))
        return ResolvedParagraph(
            runs=tuple(runs),
            style=para.style,
        )
    

    def _table(
        self,
        table: TableBlueprint,
    ) -> ResolvedTable:
        
        rows = []
        for row in table.rows:
            if isinstance(row, RowBlueprint):
                rows.append(self._row(row))
            elif isinstance(row, RowPlaceholder):
                rows.extend(self._expand_row(row))
                
        return ResolvedTable(
            rows=tuple(rows),
            style=table.style,
        )


    def _row(
        self,
        row: RowBlueprint,
    ) -> ResolvedRow:
        
        return ResolvedRow(
            cells=tuple(self._cell(c) for c in row.cells),
            style=row.style,
        )


    def _expand_row(
        self,
        row: RowPlaceholder,
    ) -> list[ResolvedRow]:
        
        table = self._context.table

        if self._mode is ResolveMode.KEYS:
            table = RAW_SINGLE_ROW

        if table is None:
            self._diag.warn(
                Layer.RENDER,
                "row_placeholder_no_data",
                "Row placeholder preset but no table data provided; skipped.",
            )
            return []
        return [
            ResolvedRow(
                cells=tuple(self._expand_cell(cell, data_row) for cell in row.cells),
                style=row.style,
            )
            for data_row in table.rows
        ]


    def _cell(
        self,
        cell,
    ) -> ResolvedCell:
        
        if isinstance(cell, CellBlueprint):
            blocks = tuple(
                b for b \
                in (self._block(x) for x in cell.blocks) \
                if b is not None
            )
            return ResolvedCell(
                blocks=blocks,
                style=cell.style,
            )
        self._diag.warn(
            Layer.RENDER,
            "unexpected_cell_placeholder",
            "Cell placeholder found in non-placeholder row; skipped.",
        )
        return ResolvedCell(
            blocks=(),
            style=cell.cell_style,
        )
    

    def _expand_cell(
        self,
        cell,
        data_row,
    ) -> ResolvedCell:
        
        if isinstance(cell, CellPlaceholder):
            value = self._column_value(cell.key, cell.language, data_row)
            para = ResolvedParagraph(
                runs=(ResolvedTextRun(text=value, style=cell.text_style, placeholder_key=cell.key),),
                style=cell.para_style,
            )
            return ResolvedCell(
                blocks=(para,),
                style=cell.cell_style,
            )
        return self._cell(cell)
    

    def _column_value(
        self,
        key: str,
        language: str,
        data_row,
    ) -> str:

        if self._mode is ResolveMode.KEYS:
            return placeholder_syntax(key)
        
        values = data_row.values.get(key)
        value = values.get(language) if values is not None else None
        if value is None:
            self._diag.warn(
                Layer.RENDER,
                "missing_column_value",
                f"Column '{key}' ({language}) missing; erndered empty.",
                key=key, language=language,
            )
            return ""
        return value


    def _block(
        self,
        block,
    ) -> ResolvedBlock | None:
        
        if isinstance(block, ParagraphBlueprint):
            return self._paragraph(block)
        
        if isinstance(block, TableBlueprint):
            return self._table(block)

        if isinstance(block, TablePlaceholder):
            if self._mode is ResolveMode.KEYS:
                return ResolvedParagraph(
                    runs=(
                        ResolvedTextRun(
                            text=placeholder_syntax(block.key),
                            style=block.text_style,
                            placeholder_key=block.key,
                        ),
                    ),
                    style=raw_paragtaph_style(),
                )
            if self._context.table is None:
                self._diag.warn(
                    Layer.RENDER,
                    "table_placeholder_no_data",
                    "invoice_table present but no table data provided; skipped.",
                )
                return None

            return build_invoice_table(block, self._context.table)
    

    def _segment_runs(
        self,
        seg,
    ) -> list[ResolvedRun]:
        
        if isinstance(seg, TextSegment):
            return [ResolvedTextRun(
                text=seg.text,
                style=seg.style,
            )]
        
        if isinstance(seg, PlaceholderSegment):
            return [ResolvedTextRun(
                text=self._value(seg.key, seg.language),
                style=seg.style,
                placeholder_key=seg.key,
            )]
        
        if isinstance(seg, JoinedPlaceholderSegment):
            # parts = [
            #     item.text if isinstance(item, TextSegment) \
            #     else self._value(item.key, item.language) \
            #     for item in seg.items
            # ]
            # text = seg.separator.join(p for p in parts if p)
            # return [ResolvedTextRun(text=text, style=seg.style)]
            
            return self._joined_runs(seg)
        
        if isinstance(seg, GroupedPlaceholderSegment):
            # groups = []
            # for group in seg.items:
            #     inner = [
            #         item.text if isinstance(item, TextSegment) \
            #         else self._value(item.key, item.language) \
            #         for item in group
            #     ]

            #     joined = " ".join(p for p in inner) if all(inner) else None      # (!) empty string from db will drop whole group, Hardcoded value here
            #     if joined:
            #         groups.append(joined)

            # return [ResolvedTextRun(
            #     text=seg.separator.join(groups),
            #     style=seg.style,
            # )]

            return self._grouped_runs(seg)
        
        if isinstance(seg, ImageSegment):
            asset = self._assets.get(seg.asset_id)
            if asset is None:
                self._diag.warn(
                    Layer.RENDER,
                    "missing_asset",
                    f"Image asset '{seg.asset_id}' not found; skipped.",
                    asset_id=seg.asset_id,
                )
                return []
            return [ResolvedImageRun(
                asset=asset,
                width_emu=seg.width_emu,
                height_emu=seg.height_emu,
            )]
        
        return []


    def _joined_runs(self, seg) -> list[ResolvedRun]:
        runs: list[ResolvedRun] = []

        for item in seg.items:
            text, key = (item.text, None) \
                if isinstance(item, TextSegment) \
                else (self._value(item.key, item.language), item.key)

            if not text:
                continue

            if runs:
                runs.append(ResolvedTextRun(text=seg.separator, style=seg.style))

            runs.append(ResolvedTextRun(
                text=text, style=seg.style, placeholder_key=key,
            ))

        return runs


    def _grouped_runs(self, seg) -> list[ResolvedRun]:
        runs: list[ResolvedRun] = []

        for group in seg.items:
            resolved = [
                (item.text, None) if isinstance(item, TextSegment)
                else (self._value(item.key, item.language), item.key)
                for item in group
            ]

            if not all(text for text, _ in resolved):
                continue        # empty part drops the whole group

            if runs:
                runs.append(ResolvedTextRun(text=seg.separator, style=seg.style))

            for index, (text, key) in enumerate(resolved):
                if index:
                    runs.append(ResolvedTextRun(text=" ", style=seg.style))
                runs.append(ResolvedTextRun(
                    text=text, style=seg.style, placeholder_key=key,
                ))

        return runs
    

    def _value(
        self,
        key: str,
        language: str,
    ) -> str:

        if self._mode is ResolveMode.KEYS:
            return placeholder_syntax(key)
        
        values = self._context.scalars.get(key)
        found = values.get(language) if values is not None else None

        if found is not None:
            return found
        
        if self._required.get(key, True):
            raise PlaceholderError(
                f"Missing required placeholder '{key}' ({language}).",
                user_message="A required value is missing.",
                context={"key": key, "language": language},
            )
        
        self._diag.warn(
            Layer.RENDER,
            "missing_placeholder",
            f"Missing optional placeholder '{key}' ({language}); rendered empty.",
            key=key, language=language,
        )

        return ""