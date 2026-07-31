from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.hashing import hash_bytes
from app.core.errors import AppError
from app.db.models.core.template import Template
from app.db.seed import SEED_DIR
from app.document_engine.blueprint.models.template import TemplateConfig
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.template.import_service import TemplateImportService
from app.services.template.repository import TemplateRepository

MANIFEST = SEED_DIR / "templates.json"
TEMPLATE_DIR = SEED_DIR / "templates"


@dataclass(slots=True, frozen=True)
class TemplateSeedResult:
    code: str
    action: str         # created | updated | unchanged | skipped | failed
    template_id: int | None = None
    detail: str | None = None


def _config(entry: dict) -> TemplateConfig:
    return TemplateConfig(
        primary_language=entry["primary_language"],
        secondary_language=entry["secondary_language"],
        type=entry["type"],
        name=entry["name"],
        description=entry["description"],
        append_currency=entry["append_currency"],
    )


def seed_default_templates(session: Session) -> list[TemplateSeedResult]:
    """Ingest the shipped .docx defaults, re-ingesting only what changed."""

    # a broken default must never stop the app from starting, so ingestion failures
    # are only reported rather than raised

    entries = json.loads(MANIFEST.read_text(encoding="UTF-8"))
    repo = TemplateRepository(session)
    results: list[TemplateSeedResult] = []

    for entry in entries:
        code = entry["code"]
        path = TEMPLATE_DIR / entry["file"]

        try:
            source_sha256 = hash_bytes(path.read_bytes())
        except OSError as e:
            results.append(TemplateSeedResult(code, "failed", detail=str(e)))
            continue

        template = session.scalars(
            select(Template).where(Template.code == code),
        ).first()

        if template is not None:
            if not template.active:
                results.append(TemplateSeedResult(
                    code, "skipped", template.id, "deactivated by user",
                ))
                continue

            if repo.current_version(template.id).source_sha256 == source_sha256:
                results.append(TemplateSeedResult(
                    code, "unchanged", template.id,
                ))
                continue

        service = TemplateImportService(
            session, DbTemplateInputProvider(session, config=_config(entry)),
        )

        try:
            ingested = service.ingest(path)

            if template is None:
                template_id = service.commit(ingested, code=code, system=True)
                action = "created"
            else:
                service.update(template.id, ingested)
                template_id, action = template.id, "updated"

        except AppError as e:
            session.rollback()
            results.append(TemplateSeedResult(code, "failed", detail=str(e)))
            continue

        results.append(TemplateSeedResult(code, action, template_id))

    return results