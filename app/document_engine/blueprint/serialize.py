from app.document_engine.blueprint.models.template import (
    TemplateBlueprint, TemplateConfig, PlaceholderDefinition,
)
from app.document_engine.blueprint.models.section import SectionBlueprint
from app.document_engine.blueprint.models.document import DocumentStyleBlueprint


def dump_blueprint(
        bp: TemplateBlueprint,
) -> tuple[list, dict, dict, dict]:
    
    sections = [ s.model_dump(mode="json") for s in bp.sections ]
    placeholders = { k: v.model_dump(mode="json") for k,v in bp.placeholders.items() }
    config = bp.config.model_dump(mode="json")
    document = bp.document.model_dump(mode="json")

    return sections, placeholders, config, document


def load_blueprint(
        sections: list,
        placeholders: dict,
        config: dict,
        document: dict | None = None,
) -> TemplateBlueprint:
    
    return TemplateBlueprint(
        sections=tuple( SectionBlueprint.model_validate(s) for s in sections ),
        placeholders={ k: PlaceholderDefinition.model_validate(v) for k,v in placeholders.items() },
        config=TemplateConfig.model_validate(config),
        document=DocumentStyleBlueprint.model_validate(document or {}),
    )