from typing import cast

from itertools import pairwise

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


###### _has_open_placeholder() was replaced with _placeholder_spans() and _merge_runs()
# def _has_open_placeholder(text: str) -> bool:
#     """True when the accumulated text ends inside an unclosed '{{ ... }}'"""
#     return text.rfind("{{") > text.rfind("}}")
############################


def _placeholder_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every closed placeholder '{{ ... }}'."""

    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)

    while i < n-1:
        if text[i] == "{" and text[i+1] == "{":
            end = text.find("}}", i+2)
            if end == -1:
                break
            spans.append((i, end + 2))
            i = end + 2
        else:
            i += 1

    return spans


def _merge_runs(runs: list[RunNode]) -> list[NormalizedTextNode]:
    """Merges adjacent runs, keeping every '{{ ... }}' in one node.
    
    Real docs get placeholders (runs) split constantly, the opening '{{' itself can be split. 
    Placeholder should keep the style of the run iti starts in.
    """

    if not runs:
        return []

    text = "".join(run.text for run in runs)

    style_at: list[RunStyle] = []
    boundaries = {0, len(text)}
    offset = 0
    for run in runs:
        style_at.extend([run.style] * len(run.text))
        offset += len(run.text)
        boundaries.add(offset)

    for start, end in _placeholder_spans(text):
        boundaries -= { b for b in boundaries if start < b < end }
        boundaries |= {start, end}

    cuts = sorted(boundaries)
    merged: list[tuple[str, RunStyle]] = []

    for start, end in pairwise(cuts):
        chunk = text[start:end]
        if not chunk:
            continue

        style = style_at[start]
        if merged and merged[-1][1] ==style:
            merged[-1] = (merged[-1][0] + chunk, style)
        else:
            merged.append((chunk, style))

    return [
        NormalizedTextNode(text=chunk, style=normalize_text_style(style))
        for chunk, style in merged
    ]


def normalize_paragraph(paragraph: ParagraphNode) -> NormalizedParagraph:

    _validate_paragraph_style_attributes(paragraph.style)

    normalized_inlines: list[NormalizedInlineNode] = []
    pending: list[RunNode] = []

    def flush_runs() -> None:
        normalized_inlines.extend(_merge_runs(pending))
        pending.clear()

    for node in paragraph.inlines:
        if isinstance(node, RunNode):
            pending.append(node)

        elif isinstance(node, ImageNode):
            flush_runs()
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


    flush_runs()

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