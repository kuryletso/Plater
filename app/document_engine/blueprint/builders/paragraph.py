from app.document_engine.blueprint.template_builder import TemplateBuilderContext
from app.document_engine.blueprint.builders.segments import image_segment_bp_from_normalized, extract_segments, text_style_bp_from_normalized
from app.document_engine.blueprint.models.paragraph import (
    ParagraphBlueprint,
    ParagraphStyleBlueprint,
    ParagraphBorderBlueprint,
    ParagraphBordersBlueprint,
    NumberingRefBlueprint,
)
from app.document_engine.blueprint.models.segment import BreakSegment, FieldSegment
from app.document_engine.normalization.models.blocks import (
    NormalizedParagraph,
    NormalizedParagraphStyle,
    NormalizedParagraphBorder,
    NormalizedParagraphBorders,
)
from app.document_engine.normalization.models.inlines import (
    NormalizedTextNode,
    NormalizedImageNode,
    NormalizedBreakNode,
    NormalizedFieldNode,
)
from app.document_engine.blueprint.errors import BlueprintBuilderError


def paragraph_borders_bp_from_normalized(
        borders: NormalizedParagraphBorders | None,
) -> ParagraphBordersBlueprint | None:

    if borders is None:
        return None

    return ParagraphBordersBlueprint(
        top=_border_bp(borders.top),
        left=_border_bp(borders.left),
        bottom=_border_bp(borders.bottom),
        right=_border_bp(borders.right),
        between=_border_bp(borders.between),
    )


def paragraph_style_bp_from_normalized(
    style: NormalizedParagraphStyle,
) -> ParagraphStyleBlueprint:
    
    return ParagraphStyleBlueprint(
        alignment=style.alignment,
        spacing_before=style.spacing_before,
        spacing_after=style.spacing_after,
        indent_left=style.indent_left,
        indent_right=style.indent_right,
        indent_first_line=style.indent_first_line,
        keep_next=style.keep_next,
        line_spacing=style.line_spacing,
        line_rule=style.line_rule,
        page_break_before=style.page_break_before,
        borders=paragraph_borders_bp_from_normalized(style.borders),
        mark=text_style_bp_from_normalized(style.mark) if style.mark is not None else None,
        numbering=NumberingRefBlueprint(
            num_id=style.numbering.num_id,
            level=style.numbering.level,
        ) if style.numbering is not None else None,
    )


def paragraph_bp_from_normalized(
    paragraph: NormalizedParagraph,
    context: TemplateBuilderContext,
) -> ParagraphBlueprint:
    
    segments = []
    for inline in paragraph.inlines:
        if isinstance(inline, NormalizedTextNode):
            segments.extend(
                extract_segments(inline, context),
            )

        elif isinstance(inline, NormalizedImageNode):
            segments.append(
                image_segment_bp_from_normalized(inline),
            )

        elif isinstance(inline, NormalizedBreakNode):
            segments.append(BreakSegment(kind=inline.kind))

        elif isinstance(inline, NormalizedFieldNode):
            segments.append(FieldSegment(
                kind=inline.kind,
                instruction=inline.instruction,
                style=text_style_bp_from_normalized(inline.style),
                cached=inline.cached,
            ))

        else:
            raise BlueprintBuilderError(
                f"Unsupported inline node type: {type(inline).__name__}."
            )

    style = paragraph_style_bp_from_normalized(paragraph.style)

    return ParagraphBlueprint(
        type="paragraph",
        segments=tuple(segments),
        style=style,
    )


def _border_bp(border: NormalizedParagraphBorder | None) -> ParagraphBorderBlueprint | None:
    if border is None:
        return None

    return ParagraphBorderBlueprint(
        style=border.style,
        size=border.size,
        space=border.space,
        color=border.color,
    )