from lxml.etree import _Element

from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.extractors.runs import parse_inline
from app.document_engine.parser.extractors.fields import FieldAssembler
from app.document_engine.parser.models.blocks import ParagraphNode
from app.document_engine.parser.models.styles import RunStyle
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_attr

WORD_NAMESPACE = NS["w"]

# Elements whose runs are ordinary text of the paragraph. Hyperlink is kept as 
# plain text. `<w:del>` is deliberately not here since its text was deleted.
TRANSPARENT = frozenset({"hyperlink", "ins", "smartTag", "customXml", "dir", "bdo"})


def parse_paragraph(
        paragraph: _Element,
        context: ParserContext,
) -> ParagraphNode:

    run_base = context.style_resolver.resolve_paragraph_run_style(paragraph)
    fields = FieldAssembler(context, run_base)

    _collect(paragraph, context, run_base, fields)

    return ParagraphNode(
        inlines=fields.finish(),
        style=context.style_resolver.resolve_paragraph_style(paragraph),
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