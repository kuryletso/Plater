from __future__ import annotations

from typing import TYPE_CHECKING

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.blueprint.models.header_footer import HeaderFooterGroupBlueprint
from app.document_engine.blueprint.models.margins import MarginsBlueprint

from app.document_engine.enums.enums import SectionType, PageOrientation

if TYPE_CHECKING:
    from app.document_engine.blueprint.models.unions import BlueprintBlock



class SectionStyleBlueprint(BlueprintBase):
    section_type: SectionType
    page_width: int             # twips
    page_height: int            # twips
    orientation: PageOrientation
    margin_header: int          # twips
    margin_footer: int          # twips
    margins: MarginsBlueprint
    title_page: bool


class SectionBlueprint(BlueprintBase):
    blocks: tuple[BlueprintBlock, ...]
    headers: HeaderFooterGroupBlueprint
    footers: HeaderFooterGroupBlueprint
    style: SectionStyleBlueprint