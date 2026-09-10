from __future__ import annotations

from lxml import etree

from app.core.diagnostics import DiagnosticCollector
from app.core.errors import Layer

from app.document_engine.rendering.resolve.models import (
    ResolvedDocument, ResolvedSection, ResolvedParagraph,
    ResolvedTable, ResolvedRow, ResolvedCell,
    ResolvedTextRun, ResolvedImageRun,
)
from app.document_engine.rendering.docx.package import DocxPackage
from app.document_engine.rendering.docx.constants import (
    CT_DOCUMENT, CT_HEADER, CT_FOOTER, CT_SETTINGS,
)
from app.document_engine.rendering.docx.rels import REL_HEADER, REL_FOOTER, REL_SETTINGS, REL_IMAGE
from app.document_engine.rendering.docx.document_xml import build_document
from app.document_engine.rendering.docx.run import build_run
from app.document_engine.rendering.docx.drawing import build_image_run, EXT_BY_MIME
from app.document_engine.rendering.docx.paragraph import build_paragraph
from app.document_engine.rendering.docx.table import build_table, build_row, build_cell
from app.document_engine.rendering.docx.section import build_sect_pr
from app.document_engine.rendering.docx.header_footer import build_header, build_footer
from app.document_engine.rendering.docx.settings_xml import build_settings
from app.document_engine.rendering.docx.xml import qn


class DocxEmitter:
    """Single-use: walks a ResolvedDocument into a DocxPackage and returns .docx bytes."""

    def __init__(
        self,
        diagnostics: DiagnosticCollector,
    ) -> None:
        
        self._diag = diagnostics
        self._pkg = DocxPackage()
        self._header_index = 0
        self._footer_index = 0
        self._owner = "word/document.xml"
        self._image_index = 0
        self._pic_id = 0


    def emit(
        self,
        document: ResolvedDocument,
    ) -> bytes:
        
        def _section_break_paragraph(sect_pr: etree._Element) -> etree._Element:
            p = etree.Element(qn("w:p"))
            ppr = etree.SubElement(p, qn("w:pPr"))
            ppr.append(sect_pr)

            return p
        
        body: list[etree._Element] = []
        last_sect_pr: etree._Element | None = None
        has_even = False

        sections = document.sections
        for i, section in enumerate(sections):
            is_last = i == len(sections) - 1
            
            self._owner = "word/document.xml"
            
            section_blocks = self._blocks(section.blocks)
            
            header_refs, footer_refs, even = self._headers_footers(section)

            has_even |= even

            sect_pr = build_sect_pr(section.style, header_refs, footer_refs)

            body.extend(section_blocks)
            if is_last:
                last_sect_pr = sect_pr
            else:
                body.append(_section_break_paragraph(sect_pr))

        if has_even:
            self._pkg.add_xml("word/settings.xml", build_settings(True), CT_SETTINGS)
            self._pkg.add_document_relationship(CT_SETTINGS, "settings.xml")

        self._pkg.add_xml("word/document.xml", build_document(body, last_sect_pr), CT_DOCUMENT)

        return self._pkg.to_bytes()
    

    def _blocks(
        self,
        blocks,
    ) -> list[etree._Element]:
        
        out: list[etree._Element] = []
        for block in blocks:
            if isinstance(block, ResolvedParagraph):
                out.append(self._paragraph(block))
            elif isinstance(block, ResolvedTable):
                out.append(self._table(block))
        return out
    

    def _image_run(
        self,
        run: ResolvedImageRun,
    ) -> etree._Element | None:
        
        ext = EXT_BY_MIME.get(run.asset.mime)
        if ext is None:
            self._diag.warn(
                Layer.RENDER,
                "unsuported_image_mime",
                f"Unsupported image type '{run.asset.mime}'; skipped.",
                mime=run.asset.mime,
            )
            return None
        
        self._image_index += 1
        target = f"media/image{self._image_index}.{ext}"
        self._pkg.add_image(f"word/{target}", run.asset.data)
        rid = self._pkg.add_relationship(self._owner, REL_IMAGE, target)
        self._pic_id += 1
        return build_image_run(rid, run.width_emu, run.height_emu, self._pic_id)



    def _paragraph(
        self,
        para: ResolvedParagraph,
    ) -> etree._Element:
        
        runs: list[etree._Element] = []
        for run in para.runs:
            if isinstance(run, ResolvedTextRun):
                runs.append(build_run(run.text, run.style))
            elif isinstance(run, ResolvedImageRun):     # TODO: Write image run builder then replace this block
                img = self._image_run(run)
                if img is not None:
                    runs.append(img)
        return build_paragraph(runs, style=para.style)
    

    def _table(
        self,
        table: ResolvedTable,
    ) -> etree._Element:
        
        rows = [self._row(r) for r in table.rows]
        return build_table(rows, table.style, self._column_count(table))
    

    def _row(
        self,
        row: ResolvedRow,
    ) -> etree._Element:
        
        return build_row([self._cell(c) for c in row.cells], row.style)
    
    def _cell(
        self,
        cell: ResolvedCell,
    ) -> etree._Element:
        
        return build_cell(self._blocks(cell.blocks), cell.style)
    

    @staticmethod
    def _column_count(table: ResolvedTable) -> int:
        if not table.rows:
            return 1
        return sum(c.style.grid_span for c in table.rows[0].cells)
    

    def _headers_footers(
        self,
        section: ResolvedSection,
    ):
        
        header_refs: list[tuple[str, str]] = []
        footer_refs: list[tuple[str, str]] = []
        has_even = False

        for variant, htype in (
            (section.headers.default, "default"),
            (section.headers.first, "first"),
            (section.headers.even, "even"),
        ):
            if variant is None:
                continue
            self._header_index += 1
            target = f"header{self._header_index}.xml"
            self._owner = f"word/{target}"
            part = build_header(self._blocks(variant.blocks))
            self._pkg.add_xml(f"word/{target}", part, CT_HEADER)
            header_refs.append((htype, self._pkg.add_document_relationship(REL_HEADER, target)))
            has_even |= htype == "even"
        
        for variant, ftype in (
            (section.footers.default, "default"),
            (section.footers.first, "first"),
            (section.footers.even, "even"),
        ):
            if variant is None:
                continue
            self._footer_index += 1
            target = f"footer{self._footer_index}.xml"
            self._owner = f"word/{target}"
            part = build_footer(self._blocks(variant.blocks))
            self._pkg.add_xml(f"word/{target}", part, CT_FOOTER)
            footer_refs.append((ftype, self._pkg.add_document_relationship(REL_FOOTER, target)))
            has_even |= ftype == "even"

        return header_refs, footer_refs, has_even