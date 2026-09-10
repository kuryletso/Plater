from app.document_engine.blueprint.models.blueprint_base import BlueprintBase
from app.document_engine.blueprint.models.section import SectionBlueprint


class PlaceholderDefinition(BlueprintBase):
    required: bool = True


class TemplateConfig(BlueprintBase):
    primary_language: str
    secondary_language: str | None
    type: str
    name: str
    description: str
    append_currency: bool
    engine_version: int = 0


class TemplateBlueprint(BlueprintBase):
    sections: tuple[SectionBlueprint, ...]
    placeholders: dict[str, PlaceholderDefinition]
    config: TemplateConfig