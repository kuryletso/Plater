from __future__ import annotations

from typing import TYPE_CHECKING

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.blueprint.models.header_footer import HeaderFooterGroupBlueprint
from app.document_engine.blueprint.models.margins import MarginsBlueprint

from app.document_engine.enums.enums import SectionType, PageOrientation

if TYPE_CHECKING:
    from app.document_engine.blueprint.models.unions import BlueprintBlock



class ColumnWidthBlueprint(BlueprintBase):
    width: int      # twips
    space: int      # twips after the column


class ColumnsBlueprint(BlueprintBase):
    count: int
    space: int = 720        # twips between equal columns
    separator: bool = False
    widths: tuple[ColumnWidthBlueprint, ...] = ()       # empty means equal widths

    def narrowest(self, text_width: int) -> int:
        """The width a block has to fit in, whichever column it lands in."""

        if self.widths:
            return min(column.width for column in self.widths)
        return (text_width - self.space * (self.count - 1)) // self.count


class SectionStyleBlueprint(BlueprintBase):
    section_type: SectionType
    page_width: int             # twips
    page_height: int            # twips
    orientation: PageOrientation
    margin_header: int          # twips
    margin_footer: int          # twips
    margins: MarginsBlueprint
    title_page: bool = False
    columns: ColumnsBlueprint | None = None     # None is a single column


class SectionBlueprint(BlueprintBase):
    blocks: tuple[BlueprintBlock, ...]
    headers: HeaderFooterGroupBlueprint
    footers: HeaderFooterGroupBlueprint
    style: SectionStyleBlueprint