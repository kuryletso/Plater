from dataclasses import dataclass

from app.document_engine.enums.enums import BreakType


@dataclass(slots=True, frozen=True)
class NormalizedTextStyle:
    bold: bool
    italic: bool
    underline: bool
    font_name: str
    font_size: int      # half-points
    color: str


@dataclass(slots=True, frozen=True)
class NormalizedTextNode:
    text: str
    style: NormalizedTextStyle


@dataclass(slots=True, frozen=True)
class NormalizedImageNode:
    asset_id: str
    width_emu: int
    height_emu: int


@dataclass(slots=True, frozen=True)
class NormalizedBreakNode:
    kind: BreakType


type NormalizedInlineNode = NormalizedTextNode | NormalizedImageNode | NormalizedBreakNode