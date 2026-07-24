from typing import cast

from app.document_engine.normalization.models.blocks import NormalizedParagraph, NormalizedParagraphStyle
from app.document_engine.normalization.models.inlines import NormalizedTextNode, NormalizedImageNode, NormalizedInlineNode, NormalizedTextStyle
from app.document_engine.normalization.style_defaults import DEFAULT_TEXT_STYLE, DEFAULT_PARAGRAPH_STYLE
from app.document_engine.normalization.errors import NormalizationFormatError

from app.document_engine.parser.models.blocks import ParagraphNode
from app.document_engine.parser.models.inlines import RunNode, RunStyle, ImageNode
from app.document_engine.parser.models.styles import ParagraphStyle

from app.document_engine.enums.enums import ParagraphAlignment
from app.document_engine.utils.overlay_dataclass import overlay_dataclass_strict



def _validate_text_style_attributes(run_style: RunStyle) -> None:

    if isinstance(run_style.font_size, int) and run_style.font_size < 1:
        raise NormalizationFormatError(
            f"Font size must be at least 1, got {run_style.font_size}"
        )


def normalize_text_style(run_style: RunStyle) -> NormalizedTextStyle:

    _validate_text_style_attributes(run_style)

    # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
    parsed_style = NormalizedTextStyle(
            bold=cast(bool, run_style.bold),
            italic=cast(bool,run_style.italic),
            underline=cast(bool,run_style.underline),
            font_name=cast(str, run_style.font_name),
            font_size=cast(int, run_style.font_size),
            color=cast(str, run_style.color),
        )

    return overlay_dataclass_strict(
        DEFAULT_TEXT_STYLE,
        parsed_style,
    )


def _validate_paragraph_style_attributes(paragraph_style: ParagraphStyle) -> None:

    if isinstance(paragraph_style.spacing_before, int) and paragraph_style.spacing_before < 0:
        raise NormalizationFormatError(
            f"Paragraph spacing_before can't be lower than 0, got {paragraph_style.spacing_before}"
        )
    if isinstance(paragraph_style.spacing_after, int) and paragraph_style.spacing_after < 0:
        raise NormalizationFormatError(
            f"Paragraph spacing_after can't be lower than 0, got {paragraph_style.spacing_after}"
        )
    if isinstance(paragraph_style.indent_left, int) and paragraph_style.indent_left < 0:
        raise NormalizationFormatError(
            f"Paragraph indent_left can't be lower than 0, got {paragraph_style.indent_left}"
        )
    if isinstance(paragraph_style.indent_right, int) and paragraph_style.indent_right < 0:
        raise NormalizationFormatError(
            f"Paragraph indent_right can't be lower than 0, got {paragraph_style.indent_right}"
        )


def _has_open_placeholder(text: str) -> bool:
    """True when the accumulated text ends inside an unclosed '{{ ... }}'"""
    return text.rfind("{{") > text.rfind("}}")


def normalize_paragraph(paragraph: ParagraphNode) -> NormalizedParagraph:

    _validate_paragraph_style_attributes(paragraph.style)

    normalized_inlines: list[NormalizedInlineNode] = []
    current_text = ""
    current_style: RunStyle | None = None

    def flush_text() -> None:
        nonlocal current_text, current_style

        if current_style is None or not current_text:
            return
        
        normalized_inlines.append(
            NormalizedTextNode(
                text=current_text,
                style=normalize_text_style(current_style),
            )
        )

        current_text = ""
        current_style = None

    for node in paragraph.inlines:

        if isinstance(node, RunNode):
            if current_style is not None and current_style == node.style:
                current_text += node.text

            elif current_style is not None and _has_open_placeholder(current_text):
                end = node.text.find("}}")
                if end == -1:
                    current_text += node.text
                else:
                    current_text += node.text[:end + 2]
                    remainder = node.text[end + 2:]
                    flush_text()
                    if remainder:
                        current_text = remainder
                        current_style = node.style
                        
            else:
                flush_text()
                current_text = node.text
                current_style = node.style

        elif isinstance(node, ImageNode):
            flush_text()
            normalized_inlines.append(
                NormalizedImageNode(
                    asset_id=node.asset_id,
                    width_emu=node.width_emu,
                    height_emu=node.height_emu,
                )
            )

        else:
            raise NormalizationFormatError(
                f"Unsupported inline node type: {type(node).__name__}."
            )
        
    flush_text()

    parsed_style = NormalizedParagraphStyle(
        # Fields may be None here; overlay_dataclass_strict() immediately applies defaults.
        alignment=cast(ParagraphAlignment, ParagraphAlignment(paragraph.style.alignment) \
            if paragraph.style.alignment is not None \
            else None),
        spacing_before=cast(int, paragraph.style.spacing_before),
        spacing_after=cast(int, paragraph.style.spacing_after),
        indent_left=cast(int, paragraph.style.indent_left),
        indent_right=cast(int, paragraph.style.indent_right),
        keep_next=cast(bool, paragraph.style.keep_next),
    )

    return NormalizedParagraph(
        inlines=tuple(normalized_inlines),
        style=overlay_dataclass_strict(
            DEFAULT_PARAGRAPH_STYLE,
            parsed_style,
        )
    )