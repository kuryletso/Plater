from typing import Literal

from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.enums.enums import PlaceholderType, BreakType, FieldType


class TextStyleBlueprint(BlueprintBase):
    bold: bool
    italic: bool
    underline: bool
    font_name: str
    font_size: int      # half-points
    color: str


class TextSegment(BlueprintBase):
    type: Literal["text"] = "text"
    text: str
    style: TextStyleBlueprint


class PlaceholderSegment(BlueprintBase):
    type: Literal["placeholder"] = "placeholder"
    key: str
    language: str
    ph_type: PlaceholderType
    style: TextStyleBlueprint


class JoinedPlaceholderSegment(BlueprintBase):
    type: Literal["placeholder_join"] = "placeholder_join"
    items: tuple[TextSegment | PlaceholderSegment, ...]
    separator: str
    style: TextStyleBlueprint


class GroupedPlaceholderSegment(BlueprintBase):
    type: Literal["placeholder_group"] = "placeholder_group"
    items: tuple[tuple[TextSegment | PlaceholderSegment, ...], ...]
    separator: str
    style: TextStyleBlueprint


class ImageSegment(BlueprintBase):
    type: Literal["image"] = "image"
    asset_id: str
    width_emu: int
    height_emu: int


class BreakSegment(BlueprintBase):
    type: Literal["break"] = "break"
    kind: BreakType


class FieldSegment(BlueprintBase):
    """A filed Word recomputes at layout time, such as the page number."""
    type: Literal["field"] = "field"
    kind: FieldType
    instruction: str
    style: TextStyleBlueprint
    cached: str = ""        # what it showed when the template was saved