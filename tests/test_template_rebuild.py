"""Rebuilding stored blueprints from their stored source (Task 23).

A blueprint is the engine's reading of a .docx, frozen at import, so engine fixes
never reach it. A rebuild re-ingests the source bytes kept in the asset store —
never the filesystem — against the config the template was imported with, since
languages are baked in at ingestion. It replaces the reading in place: the source
did not change, so it is not a new version.
"""

import pytest
from sqlalchemy.orm import Session

from app.db.models.core.assets import Asset
from app.document_engine.blueprint.models.segment import PlaceholderSegment
from app.document_engine.blueprint.models.template import TemplateConfig
from app.document_engine.blueprint.serialize import dump_blueprint
from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
from app.document_engine.version import ENGINE_VERSION
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.template.import_service import TemplateImportService
from app.services.template.rebuild_service import TemplateRebuildService
from app.services.template.repository import TemplateRepository

from tests.conftest import FixtureInputProvider, real_placeholder_defaults, restamp


@pytest.fixture
def store(session: Session, seeded_inputs, make_docx):
    """Import a generated .docx the way the dialog does; returns (id, path)."""

    def _store(paragraphs, *, secondary=None, system=False, name="rebuild.docx"):
        path = make_docx(paragraphs=paragraphs, name=name)
        service = TemplateImportService(session, DbTemplateInputProvider(
            session,
            config=TemplateConfig(
                primary_language="ENG", secondary_language=secondary,
                type="invoice", name=name, description="", append_currency=True,
            ),
        ))
        return service.commit(service.ingest(path), system=system), path

    return _store


# --- the stamp ---------------------------------------------------------------

def test_a_fresh_import_carries_the_current_engine_stamp(session: Session, store):
    template_id, _ = store(["Invoice for {{ org_name }}"])

    config = TemplateRepository(session).current_version(template_id).config

    assert config["engine_version"] == ENGINE_VERSION
    assert TemplateRebuildService(session).stale() == []


def test_an_older_stamp_is_reported_stale(session: Session, store):
    template_id, _ = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)

    assert [t.id for t in TemplateRebuildService(session).stale()] == [template_id]


def test_stale_can_be_narrowed_to_user_or_built_in_templates(session: Session, store):
    """Built-ins rebuild silently at startup; user templates are only offered."""
    user_id, _ = store(["{{ org_name }}"], name="user.docx")
    system_id, _ = store(["{{ org_name }}"], name="system.docx", system=True)
    for template_id in (user_id, system_id):
        restamp(session, template_id, 0)

    service = TemplateRebuildService(session)

    assert [t.id for t in service.stale(system=False)] == [user_id]
    assert [t.id for t in service.stale(system=True)] == [system_id]


# --- rebuilding --------------------------------------------------------------

def test_a_rebuild_replaces_the_reading_in_place(session: Session, store):
    """A version names a source document; re-reading the same bytes is not a new one."""
    template_id, _ = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)
    repo = TemplateRepository(session)
    before = repo.current_version(template_id)
    identity = (before.id, before.version, before.source_sha256)

    result = TemplateRebuildService(session).rebuild(template_id)
    after = repo.current_version(template_id)

    assert result.action == "rebuilt"
    assert (after.id, after.version, after.source_sha256) == identity
    assert after.config["engine_version"] == ENGINE_VERSION
    assert len(repo.versions(template_id)) == 1


def test_a_rebuild_keeps_the_languages_baked_in_at_import(session: Session, store):
    """Re-reading against today's defaults would turn {{ org_name.UKR }} into text."""
    template_id, _ = store(["{{ org_name.UKR }}"], secondary="UKR")
    restamp(session, template_id, 0)

    TemplateRebuildService(session).rebuild(template_id)
    blueprint = TemplateRepository(session).get_blueprint(template_id)
    segments = blueprint.sections[0].blocks[0].segments

    assert blueprint.config.secondary_language == "UKR"
    assert any(
        isinstance(s, PlaceholderSegment) and (s.key, s.language) == ("org_name", "UKR")
        for s in segments
    )


def test_a_rebuild_reads_the_stored_source_not_the_file(session: Session, store):
    template_id, path = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)
    path.unlink()

    assert TemplateRebuildService(session).rebuild(template_id).action == "rebuilt"


def test_a_failed_rebuild_leaves_the_stored_blueprint_intact(session: Session, store):
    """A rebuild must never make a template worse than the stale reading it had."""
    template_id, _ = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)
    repo = TemplateRepository(session)
    current = repo.current_version(template_id)
    sections_before = current.sections
    session.get(Asset, current.source_sha256).data = b"not a docx"
    session.commit()

    result = TemplateRebuildService(session).rebuild(template_id)
    after = repo.current_version(template_id)

    assert result.action == "failed"
    assert after.config["engine_version"] == 0
    assert after.sections == sections_before


# --- ingest_bytes ------------------------------------------------------------

def test_ingesting_bytes_matches_ingesting_the_file(real_template):
    """One code path: ingest(path) delegates to ingest_bytes()."""
    path = real_template("formatting")
    pipeline = TemplateIngestionPipeline(FixtureInputProvider(
        placeholders=real_placeholder_defaults(),
        config=TemplateConfig(
            primary_language="ENG", secondary_language=None, type="invoice",
            name="formatting", description="", append_currency=True,
        ),
    ))

    from_path = pipeline.ingest(path)
    from_bytes = pipeline.ingest_bytes(path.read_bytes(), name=path.name)

    assert from_path.source.sha256 == from_bytes.source.sha256
    assert dump_blueprint(pipeline.finalize(from_path.draft)) == \
        dump_blueprint(pipeline.finalize(from_bytes.draft))
