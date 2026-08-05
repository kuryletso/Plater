from __future__ import annotations

from typing import TYPE_CHECKING

from app.document_engine.blueprint.builders.margins import margins_bp_from_normalized
from app.document_engine.blueprint.builders.header_footer import hf_group_bp_from_normalized
from app.document_engine.blueprint.builders.paragraph import paragraph_bp_from_normalized
from app.document_engine.blueprint.builders.table import table_bp_from_normalized, promote_standalone_table

from app.document_engine.blueprint.models.section import SectionBlueprint, SectionStyleBlueprint

from app.document_engine.normalization.models.sections import NormalizedSection, NormalizedSectionStyle
from app.document_engine.normalization.models.blocks import NormalizedParagraph, NormalizedTable

if TYPE_CHECKING:
    from app.document_engine.blueprint.template_builder import TemplateBuilderContext


def section_style_bp_from_normalized(
    style: NormalizedSectionStyle,
) -> SectionStyleBlueprint:
    
    return SectionStyleBlueprint(
        section_type=style.section_type,
        page_width=style.page_width,
        page_height=style.page_height,
        orientation=style.orientation,
        margin_header=style.margin_header,
        margin_footer=style.margin_footer,
        margins=margins_bp_from_normalized(style.margins),
    )


def section_bp_from_normalized(
    section: NormalizedSection,
    context: TemplateBuilderContext,
) -> SectionBlueprint:
    
    blocks = []
    for block in section.blocks:
        if isinstance(block, NormalizedParagraph):
            blocks.append(promote_standalone_table(
                paragraph_bp_from_normalized(block, context),
                context,
            ))

        elif isinstance(block, NormalizedTable):
            blocks.append(
                table_bp_from_normalized(block, context),
            )

    headers = hf_group_bp_from_normalized(section.headers, context)
    footers = hf_group_bp_from_normalized(section.footers, context)

    style = section_style_bp_from_normalized(section.style)

    return SectionBlueprint(
        blocks=tuple(blocks),
        headers=headers,
        footers=footers,
        style=style,
    )