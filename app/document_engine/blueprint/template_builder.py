from __future__ import annotations

from typing import Any
from dataclasses import dataclass

from app.document_engine.version import ENGINE_VERSION

from app.core.diagnostics import DiagnosticCollector
from app.core.errors import Layer
from app.document_engine.blueprint.models.template import TemplateBlueprint, PlaceholderDefinition, TemplateConfig
from app.document_engine.blueprint.models.section import SectionBlueprint
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.segment import (
    GroupedPlaceholderSegment,
    JoinedPlaceholderSegment,
    PlaceholderSegment,
)
from app.document_engine.blueprint.models.table import CellBlueprint, TableBlueprint
from app.document_engine.blueprint.errors import PlaceholderSyntaxError
from app.document_engine.normalization.models.sections import NormalizedSection
from app.document_engine.enums.enums import PlaceholderType
from app.services.template.repository import TemplateRepository


@dataclass(slots=True)
class TemplateDraftConfig:
    primary_language: str
    type: str
    name: str
    secondary_language: str | None = None
    description: str = ""
    append_currency: bool = True

    @classmethod
    def from_template_config(
        cls,
        config: TemplateConfig,
    ) -> TemplateDraftConfig:
        
        return TemplateDraftConfig(
            primary_language=config.primary_language,
            secondary_language=config.secondary_language,
            type=config.type,
            name=config.name,
            description=config.description,
            append_currency=config.append_currency,
        )

    def to_template_config(self) -> TemplateConfig:
        return TemplateConfig(
            primary_language=self.primary_language,
            secondary_language=self.secondary_language,
            type=self.type,
            name=self.name,
            description=self.description,
            append_currency=self.append_currency,
            engine_version=ENGINE_VERSION,
        )


@dataclass(slots=True)
class TemplateBuilderContext:
    default_language: str
    placeholder_defaults: dict[str, dict[str, Any]]
    languages: set[str]
    placeholders: dict[str, dict]
    diagnostics: DiagnosticCollector


    def register_placeholder(
        self,
        key: str,
    ) -> PlaceholderType:
        
        if key in self.placeholder_defaults:
            default = self.placeholder_defaults[key]
            if not default.get("active", False):
                raise PlaceholderSyntaxError(
                    f"Placeholder key '{key}' is disabled."
                )

            self.placeholders.setdefault(key, default)
            return PlaceholderType(default["type"])

        raise PlaceholderSyntaxError(
            f"Not registered key in placeholder: {key}."
        )
        

@dataclass(slots=True)
class TemplateDraft:
    sections: list[SectionBlueprint]
    context: TemplateBuilderContext
    config: TemplateDraftConfig


def _warn_misplaced_columns(sections: list[SectionBlueprint], diagnostics: DiagnosticCollector) -> None:
    """Warns about COLUMN type placeholder that survived row promotion and sits outside a table row."""

    def placeholders(segment):
        if isinstance(segment, PlaceholderSegment):
            yield segment
        elif isinstance(segment, JoinedPlaceholderSegment):
            yield from (
                i for i in segment.items if isinstance(i, PlaceholderSegment)
            )
        elif isinstance(segment, GroupedPlaceholderSegment):
            for group in segment.items:
                yield from (
                    i for i in group if isinstance(i, PlaceholderSegment)
                )

    def walk(blocks) -> None:
        for block in blocks:
            if isinstance(block, ParagraphBlueprint):
                for segment in block.segments:
                    for item in placeholders(segment):
                        if item.ph_type is PlaceholderType.COLUMN:
                            diagnostics.warn(
                                Layer.BLUEPRINT,
                                "column_placeholder_outside_table",
                                f"'{item.key}' is an invoice-line placeholder and only "
                                f"works inside a table row; it will render empty.",
                                key=item.key,
                            )
            elif isinstance(block, TableBlueprint):
                for row in block.rows:
                    for cell in row.cells:
                        if isinstance(cell, CellBlueprint):
                            walk(cell.blocks)

    for section in sections:
        walk(section.blocks)
        for group in (section.headers, section.footers):
            for hf in (group.default, group.first, group.even):
                if hf is not None:
                    walk(hf.blocks)



class TemplateBuilder:

    def build_draft(
        self,
        normalized: tuple[NormalizedSection, ...],
        default_config: TemplateConfig,
        placeholder_defaults: dict[str, dict[str, Any]],
        languages: set[str],
        diagnostics: DiagnosticCollector,
    ) -> TemplateDraft:

        # Imported here (not at module level) to break the
        # template_builder -> section -> paragraph -> template_builder cycle.
        from app.document_engine.blueprint.builders.section import section_bp_from_normalized

        config = TemplateDraftConfig.from_template_config(default_config)

        context = TemplateBuilderContext(
            default_language=config.primary_language,
            placeholder_defaults=placeholder_defaults,
            languages=languages,
            placeholders={},
            diagnostics=diagnostics,
        )

        sections = [
            section_bp_from_normalized(section, context)
            for section in normalized
        ]

        _warn_misplaced_columns(sections, diagnostics)

        return TemplateDraft(
            sections=sections,
            context=context,
            config=config,
        )

    def _define_placeholders(
        self,
        placeholders: dict[str, dict],
    ) -> dict[str, PlaceholderDefinition]:
        
        return {
            k: PlaceholderDefinition(required=v.get("required", True))
            for k,v in placeholders.items()
        }
    

    def save_draft(
        self,
        draft: TemplateDraft,
    ) -> TemplateBlueprint:
        
        return TemplateBlueprint(
            sections=tuple(draft.sections),
            placeholders=self._define_placeholders(draft.context.placeholders),
            config=draft.config.to_template_config(),
        )