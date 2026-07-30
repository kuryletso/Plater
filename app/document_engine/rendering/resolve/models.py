from __future__ import annotations

from dataclasses import dataclass

from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphStyleBlueprint
from app.document_engine.blueprint.models.table import (
    TableStyleBlueprint,
    RowStyleBlueprint,
    CellStyleBlueprint,
)
from app.document_engine.blueprint.models.section import SectionStyleBlueprint
from app.document_engine.blueprint.models.template import TemplateConfig
from app.document_engine.rendering.ports import Asset


@dataclass(slots=True, frozen=True)
class ResolvedTextRun:
    text: str
    style: TextStyleBlueprint
    placeholder_key: str | None = None      # None for literal text


@dataclass(slots=True, frozen=True)
class ResolvedImageRun:
    asset: Asset
    width_emu: int
    height_emu: int


ResolvedRun = ResolvedTextRun | ResolvedImageRun


@dataclass(slots=True, frozen=True)
class ResolvedParagraph:
    runs: tuple[ResolvedRun, ...]
    style: ParagraphStyleBlueprint


@dataclass(slots=True, frozen=True)
class ResolvedCell:
    blocks: tuple[ResolvedBlock, ...]
    style: CellStyleBlueprint


@dataclass(slots=True, frozen=True)
class ResolvedRow:
    cells: tuple[ResolvedCell, ...]
    style: RowStyleBlueprint


@dataclass(slots=True, frozen=True)
class ResolvedTable:
    rows: tuple[ResolvedRow, ...]
    style: TableStyleBlueprint


ResolvedBlock = ResolvedParagraph | ResolvedTable


@dataclass(slots=True, frozen=True)
class ResolvedHeaderFooter:
    blocks: tuple[ResolvedBlock, ...]


@dataclass(slots=True, frozen=True)
class ResolvedHeaderFooterGroup:
    default: ResolvedHeaderFooter | None
    first: ResolvedHeaderFooter | None
    even: ResolvedHeaderFooter | None


@dataclass(slots=True, frozen=True)
class ResolvedSection:
    blocks: tuple[ResolvedBlock, ...]
    headers: ResolvedHeaderFooterGroup
    footers: ResolvedHeaderFooterGroup
    style: SectionStyleBlueprint


@dataclass(slots=True, frozen=True)
class ResolvedDocument:
    sections: tuple[ResolvedSection, ...]
    config: TemplateConfig