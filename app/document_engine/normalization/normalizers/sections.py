from typing import cast

from app.document_engine.normalization.models.header_footer import NormalizedHeaderFooter, NormalizedHeaderFooterGroup
from app.document_engine.normalization.models.blocks import NormalizedBlock
from app.document_engine.normalization.models.sections import NormalizedSection, NormalizedSectionStyle
from app.document_engine.normalization.normalizers.paragraphs import normalize_paragraph
from app.document_engine.normalization.normalizers.tables import normalize_table
from app.document_engine.normalization.normalizers.shared import normalize_margins
from app.document_engine.normalization.style_defaults import DEFAULT_SECTION_STYLE, DEFAULT_SECTION_MARGINS
from app.document_engine.normalization.errors import NormalizationFormatError
from app.document_engine.parser.models.blocks import SectionBreakNode, ParagraphNode, TableNode
from app.document_engine.parser.models.header_footer import HeaderFooterNode
from app.document_engine.parser.models.styles import SectionStyle
from app.document_engine.enums.enums import SectionType, PageOrientation, HeaderFooterType
from app.document_engine.utils.overlay_dataclass import overlay_dataclass_strict
from app.core.diagnostics import DiagnosticCollector


def normalize_headers_footers(
    obj: dict[HeaderFooterType, HeaderFooterNode],
    diagnostics: DiagnosticCollector,
) -> NormalizedHeaderFooterGroup:

    preset = {}

    for t in (
        HeaderFooterType.DEFAULT,
        HeaderFooterType.EVEN,
        HeaderFooterType.FIRST,
    ):

        normalized = None
        parsed = obj.get(t)

        if parsed is not None:
            blocks = []
            for block in parsed.blocks:
                if isinstance(block, ParagraphNode):
                    blocks.append(
                        normalize_paragraph(block),
                    )

                elif isinstance(block, TableNode):
                    blocks.append(
                        normalize_table(block, diagnostics),
                    )

                else:
                    raise NormalizationFormatError(
                        f"Unknown item type in header/footer {parsed}: {type(block).__name__}."
                    )

            normalized = NormalizedHeaderFooter(
                type=t,
                blocks=tuple(blocks),
            )

        preset[t] = normalized
        
    return NormalizedHeaderFooterGroup(
        default=preset.get(HeaderFooterType.DEFAULT),
        first=preset.get(HeaderFooterType.FIRST),
        even=preset.get(HeaderFooterType.EVEN),
    )


def _validate_section_style_attributes(section_style: SectionStyle) -> None:

    if isinstance(section_style.page_width, int) and section_style.page_width < 1:
        raise NormalizationFormatError(
            f"Page width must be at least 1, got {section_style.page_width}."
        )
    if isinstance(section_style.page_height, int) and section_style.page_height < 1:
        raise NormalizationFormatError(
            f"Page height must be at least 1, got {section_style.page_height}."
        )
    if isinstance(section_style.margin_header, int) and section_style.margin_header < 0:
        raise NormalizationFormatError(
            f"Page header margin can't be negative value, got {section_style.margin_header}."
        )
    if isinstance(section_style.margin_footer, int) and section_style.margin_footer < 0:
        raise NormalizationFormatError(
            f"Page footer margin can't be negative value, got {section_style.margin_footer}."
        )


def normalize_section(
    ancestor: SectionBreakNode,
    blocks: list[NormalizedBlock],
    diagnostics: DiagnosticCollector,
) -> NormalizedSection:
    
    _validate_section_style_attributes(ancestor.style)

    try:
        section_type = SectionType(ancestor.style.section_type) \
            if ancestor.style.section_type is not None \
            else None
    except ValueError as e:
        raise NormalizationFormatError(
            f"Invalid section type: {ancestor.style.section_type}."
        ) from e
    
    try:
        orientation = PageOrientation(ancestor.style.orientation) \
            if ancestor.style.orientation is not None \
            else None
    except ValueError as e:
        raise NormalizationFormatError(
            f"Invalid orientation type: {ancestor.style.orientation}."
        ) from e

    
    parsed_style = NormalizedSectionStyle(
        # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
        section_type=cast(SectionType, section_type),
        page_width=cast(int, ancestor.style.page_width),
        page_height=cast(int, ancestor.style.page_height),
        orientation=cast(PageOrientation, orientation),
        margin_header=cast(int, ancestor.style.margin_header),
        margin_footer=cast(int, ancestor.style.margin_footer),
        margins=normalize_margins(
            margins=ancestor.style.margins,
            default=DEFAULT_SECTION_MARGINS,
        ),
        title_page=cast(bool, ancestor.style.title_page),
    )

    normalized_style = overlay_dataclass_strict(
        DEFAULT_SECTION_STYLE,
        parsed_style,
    )

    return NormalizedSection(
        blocks=tuple(blocks),
        headers=normalize_headers_footers(ancestor.headers, diagnostics),
        footers=normalize_headers_footers(ancestor.footers, diagnostics),
        style=normalized_style,
    )