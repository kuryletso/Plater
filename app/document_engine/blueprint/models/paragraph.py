from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.enums.enums import ParagraphAlignment, LineSpacingRule

if TYPE_CHECKING:
    from app.document_engine.blueprint.models.unions import BlueprintSegment


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


class ParagraphBlueprint(BlueprintBase):
    type: Literal["paragraph"] = "paragraph"
    segments: tuple[BlueprintSegment, ...]
    style: ParagraphStyleBlueprint