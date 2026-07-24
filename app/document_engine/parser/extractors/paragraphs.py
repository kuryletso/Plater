from lxml.etree import _Element

from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.extractors.runs import parse_inline
from app.document_engine.parser.models.blocks import ParagraphNode
from app.document_engine.parser.namespaces import NS

WORD_NAMESPACE = NS["w"]


def parse_paragraph(
        paragraph: _Element,
        context: ParserContext,
) -> ParagraphNode:

    run_base = context.style_resolver.resolve_paragraph_run_style(paragraph)

    inlines = []
    for run in paragraph.findall("w:r", NS):
        inlines.extend(parse_inline(run, context, run_base))

    return ParagraphNode(
        inlines=inlines,
        style=context.style_resolver.resolve_paragraph_style(paragraph),
    )