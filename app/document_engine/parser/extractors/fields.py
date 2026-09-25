"""Word fields is a live page number.

Word writes a field in one of two forms:
    - `<w:fldSimple w:instr="PAGE">` wraps the runs of its last displayed result.
    - sequence of `fldChar begin`, the field code in `instrText`, `fldChar separate`, the result runs, `fldChar end`,
    that may span any number of runs, split its code mid-word, and nest.

Google Docs writes all of it into one run with no result at all; Word spreads 
it across runs and caches the result as plain text.

Page fields become FieldNodes, so the emitter can write them back as fields. 
Every other field keeps the text it last displayed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import Layer
from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.models.blocks import ParsedInlineNode
from app.document_engine.parser.models.inlines import RunNode, FieldNode
from app.document_engine.parser.models.styles import RunStyle
from app.document_engine.enums.enums import FieldType

SUPPORTED_FIELDS = {kind.value: kind for kind in FieldType}


@dataclass(slots=True, frozen=True)
class FieldChar:
    """fldChar marker: begin / separate / end."""

    kind : str


@dataclass(slots=True, frozen=True)
class InstrText:
    """Piece of field code, with the style of the run it sits in."""

    text: str
    style: RunStyle | None = None


type RunItem = ParsedInlineNode | FieldChar | InstrText


@dataclass(slots=True)
class _OpenField:
    code: list[str] = field(default_factory=list)
    style: RunStyle | None = None
    result: list[ParsedInlineNode] = field(default_factory=list)
    in_result: bool = False


class FieldAssembler:
    """Collects one paragraph's inline, turning field markup into nodes."""

    def __init__(self, context: ParserContext, run_base: RunStyle) -> None:
        self._context = context
        self._run_base = run_base
        self._nodes: list[ParsedInlineNode] = []
        self._open: list[_OpenField] = []


    def feed(self, items: list[RunItem]) -> None:
        for item in items:
            self._item(item)


    def simple(self, instruction: str, items: list[RunItem]) -> None:
        """<w:fldSimple> , the instruction is in an attribute, its runs are the result."""
        result = [item for item in items if not isinstance(item, (FieldChar, InstrText))]
        self._place(self._resolve(instruction, result, None))


    def finish(self) -> list[ParsedInlineNode]:
        """Unterminated field keeps whatever result it had shown."""

        while self._open:
            self._place(self._open.pop().result)
        return self._nodes


    def _item(self, item: RunItem) -> None:
        if isinstance(item, FieldChar):
            if item.kind == "begin":
                self._open.append(_OpenField())
            elif self._open and item.kind == "separate":
                self._open[-1].in_result = True
            elif self._open and item.kind == "end":
                closed = self._open.pop()
                self._place(self._resolve("".join(closed.code), closed.result, closed.style))
            return

        if not self._open:
            if not isinstance(item, InstrText):
                self._nodes.append(item)
            return

        current = self._open[-1]
        if isinstance(item, InstrText):
            if not current.in_result:
                # code can be split mid-word across runs, e.g. "PA" + "GE"
                current.code.append(item.text)
                current.style = current.style or item.style
        elif current.in_result:
            current.result.append(item)


    def _place(self, nodes: list[ParsedInlineNode]) -> None:
        """Finished field goes into the enclosing field's result, or the paragraph. 
        One nested in another field's *code* is part that code, not of the text.
        """

        if not self._open:
            self._nodes.extend(nodes)
        elif self._open[-1].in_result:
            self._open[-1].result.extend(nodes)


    def _resolve(
            self,
            code: str,
            result: list[ParsedInlineNode],
            style: RunStyle | None,
    ) -> list[ParsedInlineNode]:

        instruction = " ".join(code.split())        # keeps switches such as \* roman
        name = instruction.split(" ", 1)[0].upper()
        if name == "HYPERLINK":
            return result       # link is kept as plain text
        
        kind = SUPPORTED_FIELDS.get(name)
        if kind is None:
            if name:
                self._context.diagnostics.warn(
                    Layer.PARSER,
                    "field_kept_as_text",
                    f"'{name}' fields are not supported; kept as the text it last showed.",
                    field=name,
                )
            return result

        texts = [node for node in result if isinstance(node, RunNode)]
        return [FieldNode(
            kind=kind,
            instruction=instruction,
            style=style or (texts[0].style if texts else self._run_base),
            cached="".join(node.text for node in texts),
        )]