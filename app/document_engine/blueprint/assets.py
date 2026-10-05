from __future__ import annotations

from app.document_engine.blueprint.models.template import TemplateBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.table import TableBlueprint, CellBlueprint
from app.document_engine.blueprint.models.segment import ImageSegment


def collect_assets_ids(
        blueprint: TemplateBlueprint,
) -> set[str]:
    
    found: set[str] = set()

    def visit_blocks(blocks) -> None:
        for block in blocks:
            if isinstance(block, ParagraphBlueprint):
                for seg in block.segments:
                    if isinstance(seg, ImageSegment):
                        found.add(seg.asset_id)

            elif isinstance(block, TableBlueprint):
                for row in block.rows:
                    for cell in row.cells:
                        if isinstance(cell, CellBlueprint):
                            visit_blocks(cell.blocks)


    for section in blueprint.sections:
        visit_blocks(section.blocks)
        for group in (section.headers, section.footers):
            for hf in (group.default, group.first, group.even):
                if hf is not None:
                    visit_blocks(hf.blocks)

    for font in blueprint.document.fonts:
        for _, face in font.faces():
            found.add(face.asset_id)

    return found