from dataclasses import dataclass

from app.document_engine.parser.models.styles import RunStyle
from app.document_engine.enums.enums import BreakType

@dataclass(slots=True, frozen=True)
class RunNode:
    text: str
    style: RunStyle


@dataclass(slots=True, frozen=True)
class ImageNode:
    asset_id: str
    width_emu: int
    height_emu: int


@dataclass(slots=True, frozen=True)
class BreakNode:
    """Page or column break, not text."""
    kind: BreakType