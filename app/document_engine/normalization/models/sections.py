from dataclasses import dataclass

from app.document_engine.normalization.models.blocks import NormalizedBlock
from app.document_engine.normalization.models.header_footer import NormalizedHeaderFooterGroup
from app.document_engine.normalization.models.shared import NormalizedMargins

from app.document_engine.enums.enums import SectionType, PageOrientation


@dataclass(slots=True, frozen=True)
class NormalizedSectionStyle:
    section_type: SectionType
    page_width: int             # twips
    page_height: int            # twips
    orientation: PageOrientation
    margin_header: int          # twips
    margin_footer: int          # twips
    margins: NormalizedMargins
    title_page: bool


@dataclass(slots=True, frozen=True)
class NormalizedSection:
    blocks: tuple[NormalizedBlock, ...]
    headers: NormalizedHeaderFooterGroup
    footers: NormalizedHeaderFooterGroup
    style: NormalizedSectionStyle