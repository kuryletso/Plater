import re
from dataclasses import replace

from lxml import etree
from lxml.etree import _Element

from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.extractors.runs import parse_inline
from app.document_engine.parser.extractors.fields import FieldAssembler
from app.document_engine.parser.extractors.styles import extract_paragraph_style
from app.document_engine.parser.models.blocks import ParagraphNode
from app.document_engine.parser.models.styles import RunStyle, ParagraphStyle, ParagraphBorderStyle
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_attr
from app.core.errors import Layer

WORD_NAMESPACE = NS["w"]

# Elements whose runs are ordinary text of the paragraph. Hyperlink is kept as 
# plain text. `<w:del>` is deliberately not here since its text was deleted.
TRANSPARENT = frozenset({"hyperlink", "ins", "smartTag", "customXml", "dir", "bdo"})

# VML horizontal rule: Google Docs Insert -> Horizontal line, Word Borders -> Horizontal Line
_RULES = etree.XPath(".//w:pict/*[@o:hr][not(ancestor::w:del)]", namespaces=NS)
_VML_TRUE = frozenset({"t", "true", "on", "1"})
_NO_BORDER = frozenset({"nil", "none"})
_RULE_HEIGHT = re.compile(r"height\s*:\s*(\d*\.?\d+)\s*(pt|px|in|cm|mm|pc)?")
_POINTS_PER_UNIT = {"pt": 1.0, "px": 0.75, "in": 72.0, "cm": 72 / 2.54, "mm": 72 / 25.4, "pc": 12.0}
_HEX_COLOR = re.compile(r"#?([0-9A-Fa-f]{6})")
_RULE_GREY = "A0A0A0"       # default for no color


def parse_paragraph(
        paragraph: _Element,
        context: ParserContext,
) -> ParagraphNode:

    run_base = context.style_resolver.resolve_paragraph_run_style(paragraph)
    fields = FieldAssembler(context, run_base)
    
    _collect(paragraph, context, run_base, fields)

    properties = paragraph.find("w:pPr", NS)
    mark = context.style_resolver.resolve_run_style(properties, run_base) \
        if properties is not None else run_base
    
    return ParagraphNode(
        inlines=fields.finish(),
        style=_with_numbering(
            _with_rule(context.style_resolver.resolve_paragraph_style(paragraph), paragraph),
            paragraph,
            context,
        ),
        mark=mark,
    )


def _collect(
        container: _Element,
        context: ParserContext,
        run_base: RunStyle,
        fields: FieldAssembler,
) -> None:
    """Feed a container's runs to the assembler, descending into every element 
    that holds runs of its own.
    
    Hyperlinks, content controls and tracked insertions 
    all wrap ordinary text, and skipping them loses it.
    """

    for child in container:
        name = _local_name(child)

        if name == "r":
            fields.feed(parse_inline(child, context, run_base))

        elif name == "fldSimple":
            # its runs are children of the field, not of the paragraph
            fields.simple(
                get_attr(child, "instr") or "",
                [
                    item
                    for run in child.findall("w:r", NS)
                    for item in parse_inline(run, context, run_base)
                ],
            )

        elif name == "sdt":
            content = child.find("w:sdtContent", NS)
            if content is not None:
                _collect(content, context, run_base, fields)

        elif name in TRANSPARENT:
            _collect(child, context, run_base, fields)


def _local_name(element: _Element) -> str | None:
    """The 'w:' local name, or None for comments and other namespaces."""

    prefix = f"{{{WORD_NAMESPACE}}}"
    tag = element.tag
    return tag[len(prefix):] if isinstance(tag, str) and tag.startswith(prefix) else None


def _with_rule(style: ParagraphStyle, paragraph: _Element) -> ParagraphStyle:
    rule = next(
        (shape for shape in _RULES(paragraph) if shape.get(f"{{{NS['o']}}}hr") in _VML_TRUE),
        None,
    )
    if rule is None:
        return style
    if style.border_bottom is not None and style.border_bottom.style not in _NO_BORDER:
        return style

    return replace(style, border_bottom=ParagraphBorderStyle(
        style="single",
        size=_rule_size(rule.get("style")),
        space=0,
        color=_rule_color(rule.get("fillcolor")),
    ))


def _rule_size(css: str | None) -> int:
    """The rule's height in eights of a point, clamped to what Word draws for a line border."""

    match = _RULE_HEIGHT.search(css or "")
    points = float(match.group(1)) * _POINTS_PER_UNIT[match.group(2) or "px"] if match else 1.5
    return min(max(round(points * 8), 2), 96)


def _rule_color(fill: str | None) -> str:
    match = _HEX_COLOR.fullmatch(fill or "")        # VML allows color names; those will fallback to grey
    return match.group(1).upper() if match else _RULE_GREY


def _with_numbering(style: ParagraphStyle, paragraph: _Element, context: ParserContext) -> ParagraphStyle:
    """The list a paragraph belongs to, and the indent that comes with it.
    
    Word applies a list level's indent over the paragraph style' and under the 
    paragraph's own. Direct formatting, then numbering, the the style. Word's list 
    styles set no indent of their own, so without the level's their items would sit flush left.
    """

    if style.num_id is None:
        return style
    # numId 0 switches off the numbering a style gives
    if style.num_id == 0:
        return replace(style, num_id=None, num_level=None)

    level_id = style.num_level or 0
    level = context.numbering.level(style.num_id, level_id)
    if level is None:
        context.diagnostics.warn(
            Layer.PARSER,
            "numbering_missing",
            f"List {style.num_id} has no level {level_id}; the paragraph is left unnumbered.",
            num_id=style.num_id,
            level=level_id,
        )
        return replace(style, num_id=None, num_level=None)

    context.numbering_used.add(style.num_id)
    direct = extract_paragraph_style(paragraph.find("w:pPr", NS))

    return replace(
        style,
        num_level=level_id,
        indent_left=_first(direct.indent_left, level.indent_left, style.indent_left),
        indent_first_line=_first(direct.indent_first_line, level.indent_first_line, style.indent_first_line),
    )


def _first(*values: int | None) -> int | None:
    return next((v for v in values if v is not None), None)