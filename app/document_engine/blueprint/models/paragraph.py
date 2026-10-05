from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.enums.enums import ParagraphAlignment, LineSpacingRule, TableBorderStyleEnum

if TYPE_CHECKING:
    from app.document_engine.blueprint.models.unions import BlueprintSegment


class ParagraphBorderBlueprint(BlueprintBase):
    style: TableBorderStyleEnum
    size: int       # eights of a point
    space: int      # points between the border and text
    color: str


class ParagraphBordersBlueprint(BlueprintBase):
    top: ParagraphBorderBlueprint | None = None
    left: ParagraphBorderBlueprint | None = None
    bottom: ParagraphBorderBlueprint | None = None
    right: ParagraphBorderBlueprint | None = None
    between: ParagraphBorderBlueprint | None = None


class NumberingRefBlueprint(BlueprintBase):
    """The list a paragraph belongs to: <w:num> of the document's numbering."""

    num_id: int
    level: int = 0


class ParagraphStyleBlueprint(BlueprintBase):
    alignment: ParagraphAlignment
    spacing_before: int         # twips
    spacing_after: int          # twips
    indent_left: int            # twips
    indent_right: int           # twips
    keep_next: bool
    line_spacing: int = 240     # 240ths of a line (auto) or twips (exact / atLeast)
    line_rule: LineSpacingRule = LineSpacingRule.AUTO
    page_break_before: bool = False
    borders: ParagraphBordersBlueprint | None = None
    indent_first_line: int = 0
    mark: TextStyleBlueprint | None = None
    numbering: NumberingRefBlueprint | None = None


class ParagraphBlueprint(BlueprintBase):
    type: Literal["paragraph"] = "paragraph"
    segments: tuple[BlueprintSegment, ...]
    style: ParagraphStyleBlueprint