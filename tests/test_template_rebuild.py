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
from app.services.errors import BlueprintUnreadable, InvalidSelection
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.template.import_service import TemplateImportService
from app.services.template.rebuild_service import BlueprintState, TemplateRebuildService
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


# --- blueprint state (23d) ----------------------------------------------------

def make_unreadable(session: Session, template_id: int) -> None:
    """Corrupt a stored blueprint the way a model change would: drop a required key."""

    version = TemplateRepository(session).current_version(template_id)
    version.sections = [
        {key: value for key, value in section.items() if key != "style"}
        for section in version.sections
    ]
    session.commit()


def test_a_current_template_reports_ok(session: Session, store):
    template_id, _ = store(["Invoice for {{ org_name }}"])

    assert TemplateRebuildService(session).state(template_id) is BlueprintState.OK


def test_an_old_stamp_reports_stale(session: Session, store):
    template_id, _ = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)

    assert TemplateRebuildService(session).state(template_id) is BlueprintState.STALE


def test_a_blueprint_that_no_longer_validates_reports_unreadable(session: Session, store):
    template_id, _ = store(["Invoice for {{ org_name }}"])
    make_unreadable(session, template_id)

    assert TemplateRebuildService(session).state(template_id) is BlueprintState.UNREADABLE


def test_loading_an_unreadable_blueprint_raises_a_service_error(session: Session, store):
    """pydantic's ValidationError is not an AppError, so every GUI guard misses it."""

    template_id, _ = store(["Invoice for {{ org_name }}"])
    make_unreadable(session, template_id)

    with pytest.raises(BlueprintUnreadable) as caught:
        TemplateRepository(session).get_blueprint(template_id)

    assert caught.value.user_message
    assert caught.value.context["template_id"] == template_id


def test_rebuilding_repairs_an_unreadable_blueprint(session: Session, store):
    """The rebuild reads the source and the config dict, never the stored blueprint."""

    template_id, _ = store(["Invoice for {{ org_name }}"])
    make_unreadable(session, template_id)

    assert TemplateRebuildService(session).rebuild(template_id).action == "rebuilt"
    assert TemplateRebuildService(session).state(template_id) is BlueprintState.OK


# --- restore re-reads the source ---------------------------------------------

def add_version(session: Session, template_id: int, paragraphs, make_docx, name="v2.docx"):
    repository = TemplateRepository(session)
    template = repository.get(template_id)
    config = repository.current_version(template_id).config

    service = TemplateImportService(session, DbTemplateInputProvider(
        session,
        config=TemplateConfig(
            primary_language=config["primary_language"],
            secondary_language=config.get("secondary_language"),
            type=template.type, name=template.name,
            description="", append_currency=True,
        ),
    ))
    return service.commit_version(
        template_id, service.ingest(make_docx(paragraphs=paragraphs, name=name)),
    )


def test_restore_appends_a_fresh_reading_of_the_old_source(session: Session, store,
                                                           make_docx):
    template_id, _ = store(["v1 {{ org_name }}"], name="v1.docx")
    add_version(session, template_id, ["v2 {{ org_name }}"], make_docx)
    restamp(session, template_id, 0)

    outcome = TemplateRebuildService(session).restore(template_id, 1)
    repository = TemplateRepository(session)
    current = repository.current_version(template_id)

    assert outcome.action == "restored"
    assert current.version == 3
    assert current.source_sha256 == repository.version(template_id, 1).source_sha256
    assert current.config["engine_version"] == ENGINE_VERSION


def test_restoring_a_built_in_is_refused(session: Session, store):
    """A precondition, so it raises rather than returning a failed result."""

    template_id, _ = store(["Invoice for {{ org_name }}"], system=True)

    with pytest.raises(InvalidSelection):
        TemplateRebuildService(session).restore(template_id, 1)


# --- the warning reaches the preview -----------------------------------------

def test_preview_warns_that_a_template_is_stale(session: Session, store, make_org,
                                                make_sequence, make_line_input):
    """It rides the normal diagnostics, so the preview panel shows it with no UI work."""

    from app.services.invoice.generate import InvoiceGenerateService
    from tests.test_services_assembler import make_draft

    template_id, _ = store(["Invoice for {{ org_name }}"])
    restamp(session, template_id, 0)

    provider = make_org("Provider Co", tax_value="11111111")
    client = make_org("Client Co", tax_value="22222222")
    sequence = make_sequence(provider)
    draft = make_draft(
        provider, client, sequence, (make_line_input(),), template_id=template_id,
    )

    result = InvoiceGenerateService(session).preview(draft)

    assert "stale_blueprint" in [item.code for item in result.diagnostics.items]
