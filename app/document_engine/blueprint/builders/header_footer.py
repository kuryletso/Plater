from app.document_engine.blueprint.template_builder import TemplateBuilderContext
from app.document_engine.blueprint.builders.paragraph import paragraph_bp_from_normalized
from app.document_engine.blueprint.builders.table import table_bp_from_normalized, promote_standalone_table
from app.document_engine.blueprint.models.header_footer import HeaderFooterGroupBlueprint, HeaderFooterBlueprint

from app.document_engine.normalization.models.header_footer import NormalizedHeaderFooterGroup, NormalizedHeaderFooter
from app.document_engine.normalization.models.blocks import NormalizedParagraph, NormalizedTable


def hf_bp_from_normalized(
    header_footer: NormalizedHeaderFooter | None,
    context: TemplateBuilderContext,
) -> HeaderFooterBlueprint | None:
    
    if header_footer is None:
        return None

    blocks = []
    for block in header_footer.blocks:
        if isinstance(block, NormalizedParagraph):
            blocks.append(promote_standalone_table(
                paragraph_bp_from_normalized(
                    block,
                    context,
                ),
                context,
            ))

        elif isinstance(block, NormalizedTable):
            blocks.append(
                table_bp_from_normalized(
                    block,
                    context,
                ),
            )

    return HeaderFooterBlueprint(
        type=header_footer.type,
        blocks=tuple(blocks),
    )


def hf_group_bp_from_normalized(
    hf_group: NormalizedHeaderFooterGroup,
    context: TemplateBuilderContext,
) -> HeaderFooterGroupBlueprint:

    return HeaderFooterGroupBlueprint(
        default=hf_bp_from_normalized(hf_group.default, context),
        first=hf_bp_from_normalized(hf_group.first, context),
        even=hf_bp_from_normalized(hf_group.even, context),
    )