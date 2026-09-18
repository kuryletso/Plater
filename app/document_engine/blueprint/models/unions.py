from typing import Annotated

from pydantic import Field

from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.segment import (
    TextSegment,
    PlaceholderSegment,
    JoinedPlaceholderSegment,
    GroupedPlaceholderSegment,
    ImageSegment,
    BreakSegment,
)
from app.document_engine.blueprint.models.table import (
    TableBlueprint,
    TablePlaceholder,
    RowBlueprint,
    RowPlaceholder,
    CellBlueprint,
    CellPlaceholder,
)


BlueprintSegment = Annotated[
    TextSegment
    | PlaceholderSegment
    | JoinedPlaceholderSegment
    | GroupedPlaceholderSegment
    | ImageSegment
    | BreakSegment,
    Field(discriminator="type"),
]


BlueprintCell = Annotated[
    CellBlueprint
    | CellPlaceholder,
    Field(discriminator="type"),
]


BlueprintRow = Annotated[
    RowBlueprint
    | RowPlaceholder,
    Field(discriminator="type"),
]


BlueprintBlock = Annotated[
    ParagraphBlueprint
    | TableBlueprint
    | TablePlaceholder,
    Field(discriminator="type"),
]