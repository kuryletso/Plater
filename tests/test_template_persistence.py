"""Blueprint serialization, versioned template persistence, asset GC and the import service."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.provider import DbAssetProvider
from app.assets.service import AssetBlob
from app.db.associations import template_version_asset_m2m
from app.db.models.core.assets import Asset
from app.db.models.core.template import Template
from app.db.models.core.template_version import TemplateVersion
from app.document_engine.blueprint.assets import collect_assets_ids
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.segment import (
    ImageSegment, PlaceholderSegment, TextSegment,
)
from app.document_engine.blueprint.models.template import TemplateBlueprint, TemplateConfig
from app.document_engine.blueprint.serialize import dump_blueprint, load_blueprint
from app.document_engine.enums.enums import PlaceholderType
from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
from app.services.errors import EntityNotFound
from app.services.template.db_input_provider import DbTemplateInputProvider
from app.services.template.import_service import TemplateImportService
from app.services.template.repository import TemplateRepository


@pytest.fixture
def blueprint(make_docx, make_png, fixture_provider) -> TemplateBlueprint:
    """A blueprint built from a real .docx containing text, placeholders, a table and an image."""
    path = make_docx(
        paragraphs=["Invoice for {{ org_name }}", "No. {{ invoice_no.UKR }}"],
        table=[["Item", "Total"]],
        image=make_png(),
    )
    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(path)
    return pipeline.finalize(result.draft)


@pytest.fixture
def ingested(make_docx, make_png, fixture_provider):
    """(blueprint, asset bundle, source sha256) from a template that embeds one image."""
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"], image=make_png())
    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(path)
    return pipeline.finalize(result.draft), result.assets, result.source_sha256


@pytest.fixture
def other_ingested(make_docx, make_png, fixture_provider):
    """A second template with a *different* image, for cross-template asset tests."""
    path = make_docx(
        paragraphs=["Quote for {{ org_name }}"],
        image=make_png(name="other.png", color=(10, 200, 90)),
        name="other.docx",
    )
    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(path)
    return pipeline.finalize(result.draft), result.assets, result.source_sha256


def segments_of(bp: TemplateBlueprint) -> list:
    out = []
    for section in bp.sections:
        for block in section.blocks:
            if isinstance(block, ParagraphBlueprint):
                out.extend(block.segments)
    return out


def links_of(session: Session, version_id: int) -> set[str]:
    return set(session.execute(
        select(template_version_asset_m2m.c.asset_sha256)
        .where(template_version_asset_m2m.c.template_version_id == version_id)
    ).scalars().all())


def versions_of(session: Session, template_id: int) -> list[int]:
    return list(session.scalars(
        select(TemplateVersion.version)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version)
    ).all())


# --- serialization -----------------------------------------------------------

def test_dump_produces_json_serializable_structures(blueprint):
    """mode='json' must flatten enums; otherwise the JSON column write fails."""
    sections, placeholders, config = dump_blueprint(blueprint)

    json.dumps(sections)
    json.dumps(placeholders)
    json.dumps(config)


def test_blueprint_survives_a_dump_load_round_trip(blueprint):
    assert load_blueprint(*dump_blueprint(blueprint)) == blueprint


def test_round_trip_preserves_discriminated_segment_types(blueprint):
    """The riskiest part: unions must rebuild as their concrete classes, not dicts."""
    restored = load_blueprint(*dump_blueprint(blueprint))

    rebuilt = [type(s) for s in segments_of(restored)]

    assert rebuilt == [type(s) for s in segments_of(blueprint)]
    assert PlaceholderSegment in rebuilt
    assert ImageSegment in rebuilt
    assert TextSegment in rebuilt


def test_round_trip_preserves_placeholder_language_and_type(blueprint):
    restored = load_blueprint(*dump_blueprint(blueprint))

    by_key = {s.key: s for s in segments_of(restored) if isinstance(s, PlaceholderSegment)}

    assert by_key["invoice_no"].language == "UKR"
    assert by_key["org_name"].language == "ENG"              # default language
    assert by_key["org_name"].ph_type is PlaceholderType.SCALAR


def test_round_trip_preserves_image_asset_id_and_size(blueprint):
    restored = load_blueprint(*dump_blueprint(blueprint))

    original = [s for s in segments_of(blueprint) if isinstance(s, ImageSegment)][0]
    rebuilt = [s for s in segments_of(restored) if isinstance(s, ImageSegment)][0]

    assert rebuilt.asset_id == original.asset_id
    assert (rebuilt.width_emu, rebuilt.height_emu) == (original.width_emu, original.height_emu)


def test_round_trip_preserves_config_and_placeholder_definitions(blueprint):
    restored = load_blueprint(*dump_blueprint(blueprint))

    assert restored.config == blueprint.config
    assert restored.placeholders == blueprint.placeholders


# --- create ------------------------------------------------------------------

def test_create_writes_queryable_template_columns(session: Session, ingested):
    bp, bundle, sha = ingested

    template_id = TemplateRepository(session).create(bp, bundle, sha)

    row = session.get(Template, template_id)
    assert row.name == bp.config.name
    assert row.type == bp.config.type
    assert row.created_at is not None
    assert row.system is False
    assert row.active is True
    assert row.code is None


def test_create_records_a_system_template_under_its_code(session: Session, ingested):
    bp, bundle, sha = ingested

    template_id = TemplateRepository(session).create(
        bp, bundle, sha, code="default_invoice", system=True,
    )

    row = session.get(Template, template_id)
    assert row.code == "default_invoice"
    assert row.system is True


def test_create_starts_at_version_one_with_the_source_hash(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, sha)

    assert versions_of(session, template_id) == [1]
    assert repo.current_version(template_id).source_sha256 == sha


def test_saved_blueprint_round_trips_through_the_database(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, sha)
    session.expunge_all()                       # force a real reload, not identity-map cache

    assert repo.get(template_id) == bp


def test_create_persists_referenced_asset_blobs(session: Session, ingested):
    bp, bundle, sha = ingested
    (asset_sha,) = collect_assets_ids(bp)

    TemplateRepository(session).create(bp, bundle, sha)

    stored = session.get(Asset, asset_sha)
    assert stored.data == bundle[asset_sha].data
    assert stored.mime_type == "image/png"
    assert stored.size_bytes == len(bundle[asset_sha].data)


def test_assets_are_linked_to_the_version_not_the_template(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, sha)

    assert links_of(session, repo.current_version(template_id).id) == collect_assets_ids(bp)


def test_create_ignores_bundle_entries_the_blueprint_does_not_reference(session: Session, ingested):
    """A parsed-but-dropped image must not leave an orphan BLOB behind."""
    bp, bundle, sha = ingested
    padded = dict(bundle) | {
        "deadbeef": AssetBlob(sha256="deadbeef", mime_type="image/png", data=b"unused"),
    }

    TemplateRepository(session).create(bp, padded, sha)

    assert session.get(Asset, "deadbeef") is None
    assert len(session.scalars(select(Asset)).all()) == 1


def test_two_templates_sharing_an_image_store_one_blob(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)

    repo.create(bp, bundle, sha)
    repo.create(bp, bundle, sha)

    assert len(session.scalars(select(Asset)).all()) == 1
    assert len(session.scalars(select(Template)).all()) == 2


def test_get_raises_for_unknown_template(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).get(9999)


def test_current_version_raises_when_there_are_none(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).current_version(9999)


# --- versions ----------------------------------------------------------------

def test_add_version_appends_and_returns_the_new_number(session: Session,
                                                        ingested, other_ingested):
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    version = repo.add_version(template_id, other_bp, other_bundle, other_sha)

    assert version == 2
    assert versions_of(session, template_id) == [1, 2]


def test_get_returns_the_newest_version(session: Session, ingested, other_ingested):
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    repo.add_version(template_id, other_bp, other_bundle, other_sha)
    session.expunge_all()

    assert repo.get(template_id) == other_bp


def test_each_version_links_its_own_assets(session: Session, ingested, other_ingested):
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)
    first = repo.current_version(template_id).id

    repo.add_version(template_id, other_bp, other_bundle, other_sha)
    second = repo.current_version(template_id).id

    assert links_of(session, first) == collect_assets_ids(bp)
    assert links_of(session, second) == collect_assets_ids(other_bp)
    assert links_of(session, first) != links_of(session, second)


def test_history_is_pruned_to_the_retention_limit(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    for _ in range(repo.KEEP_VERSIONS + 2):
        repo.add_version(template_id, bp, bundle, sha)

    kept = versions_of(session, template_id)
    assert len(kept) == repo.KEEP_VERSIONS
    assert kept == sorted(kept)[-repo.KEEP_VERSIONS:]        # the newest survive


def test_pruning_drops_the_asset_links_of_removed_versions(session: Session,
                                                           ingested, other_ingested):
    """An image used only by a pruned version must not keep its BLOB alive."""
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)

    template_id = repo.create(other_bp, other_bundle, other_sha)   # v1 uses the other image
    for _ in range(repo.KEEP_VERSIONS):
        repo.add_version(template_id, bp, bundle, sha)             # push v1 out of retention

    (dropped_asset,) = collect_assets_ids(other_bp)
    (kept_asset,) = collect_assets_ids(bp)

    assert session.get(Asset, dropped_asset) is None
    assert session.get(Asset, kept_asset) is not None


def test_an_asset_shared_by_two_versions_survives_pruning_one(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)
    (asset_sha,) = collect_assets_ids(bp)

    for _ in range(repo.KEEP_VERSIONS + 1):
        repo.add_version(template_id, bp, bundle, sha)

    assert session.get(Asset, asset_sha) is not None


def test_restore_copies_an_old_version_forward(session: Session, ingested, other_ingested):
    """History stays append-only: restoring v1 creates a new newest version."""
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)
    repo.add_version(template_id, other_bp, other_bundle, other_sha)

    version = repo.restore(template_id, 1)
    session.expunge_all()

    assert version == 3
    assert versions_of(session, template_id) == [1, 2, 3]
    assert repo.get(template_id) == bp


def test_restore_carries_the_original_source_hash(session: Session, ingested, other_ingested):
    bp, bundle, sha = ingested
    other_bp, other_bundle, other_sha = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)
    repo.add_version(template_id, other_bp, other_bundle, other_sha)

    repo.restore(template_id, 1)

    assert repo.current_version(template_id).source_sha256 == sha


def test_restore_raises_for_an_unknown_version(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    with pytest.raises(EntityNotFound):
        repo.restore(template_id, 99)


# --- delete + asset GC -------------------------------------------------------

def test_delete_removes_the_template_its_versions_and_links(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    repo.delete(template_id)

    assert session.get(Template, template_id) is None
    assert versions_of(session, template_id) == []
    assert session.execute(select(template_version_asset_m2m)).all() == []


def test_delete_collects_the_now_orphaned_asset(session: Session, ingested):
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, sha)

    repo.delete(template_id)

    assert session.scalars(select(Asset)).all() == []


def test_shared_asset_survives_until_its_last_template_is_deleted(session: Session, ingested):
    """The reference-counting rule: an asset dies only with its final referent."""
    bp, bundle, sha = ingested
    repo = TemplateRepository(session)
    first, second = repo.create(bp, bundle, sha), repo.create(bp, bundle, sha)
    (asset_sha,) = collect_assets_ids(bp)

    repo.delete(first)
    assert session.get(Asset, asset_sha) is not None, "still referenced by the second template"

    repo.delete(second)
    assert session.get(Asset, asset_sha) is None, "last reference gone -> collected"


def test_delete_raises_for_unknown_template(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).delete(9999)


# --- asset provider (render side) --------------------------------------------

def test_db_asset_provider_reads_back_a_saved_blob(session: Session, ingested):
    bp, bundle, sha = ingested
    TemplateRepository(session).create(bp, bundle, sha)
    (asset_sha,) = collect_assets_ids(bp)

    asset = DbAssetProvider(session).get(asset_sha)

    assert asset.data == bundle[asset_sha].data
    assert asset.mime == "image/png"


def test_db_asset_provider_returns_none_for_unknown_asset(session: Session):
    assert DbAssetProvider(session).get("nope") is None


# --- DbTemplateInputProvider -------------------------------------------------

def test_input_provider_maps_the_default_config_row(session: Session, seeded_inputs):
    config = DbTemplateInputProvider(session).default_template_config()

    assert config.primary_language == "ENG"
    assert config.secondary_language == "UKR"
    assert config.type == "invoice"
    assert config.name == "Default invoice"
    assert config.append_currency is True


def test_input_provider_derives_languages_from_the_config(session: Session, seeded_inputs):
    assert DbTemplateInputProvider(session).languages() == {"ENG", "UKR"}


def test_input_provider_prefers_an_injected_config(session: Session, seeded_inputs):
    """The GUI picks languages before import; the injected config must win over the DB row."""
    injected = TemplateConfig(
        primary_language="UKR", secondary_language=None,
        type="act", name="chosen", description="", append_currency=False,
    )
    provider = DbTemplateInputProvider(session, config=injected)

    assert provider.default_template_config() is injected
    assert provider.languages() == {"UKR"}


def test_input_provider_raises_when_defaults_are_missing(session: Session):
    with pytest.raises(EntityNotFound):
        DbTemplateInputProvider(session).default_template_config()


def test_placeholder_defaults_expose_the_keys_the_builder_needs(session: Session, seeded_inputs):
    defaults = DbTemplateInputProvider(session).placeholder_defaults()

    assert defaults["org_name"] == {
        "active": True, "required": True, "type": PlaceholderType.SCALAR,
    }


def test_placeholder_defaults_include_inactive_rows(session: Session, seeded_inputs):
    """Kept so the builder can say 'disabled' rather than 'unknown key'."""
    assert DbTemplateInputProvider(session).placeholder_defaults()["retired_key"]["active"] is False


def test_disabled_placeholder_is_rejected_at_ingestion(session, seeded_inputs, make_docx):
    path = make_docx(paragraphs=["Hello {{ retired_key }}"])
    pipeline = TemplateIngestionPipeline(DbTemplateInputProvider(session))

    result = pipeline.ingest(path)

    assert len(result.diagnostics.warnings) == 1
    assert "retired_key" not in result.draft.context.placeholders


# --- import service ----------------------------------------------------------

def test_ingest_does_not_touch_the_database(session: Session, seeded_inputs,
                                            make_docx, make_png):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"], image=make_png())
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    service.ingest(path)

    assert session.scalars(select(Template)).all() == []
    assert session.scalars(select(Asset)).all() == []


def test_ingest_reports_the_source_hash(session: Session, seeded_inputs, make_docx):
    """The hash drives default-template re-seeding, so it must reach the caller."""
    from app.assets.hashing import hash_bytes

    path = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    result = service.ingest(path)

    assert result.source_sha256 == hash_bytes(path.read_bytes())


def test_commit_persists_the_reviewed_draft(session: Session, seeded_inputs,
                                            make_docx, make_png):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"], image=make_png())
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    template_id = service.commit(service.ingest(path))

    assert session.get(Template, template_id) is not None
    assert len(session.scalars(select(Asset)).all()) == 1
    assert "org_name" in TemplateRepository(session).get(template_id).placeholders


def test_commit_can_mark_a_shipped_default(session: Session, seeded_inputs, make_docx):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    template_id = service.commit(service.ingest(path), code="default_invoice", system=True)

    row = session.get(Template, template_id)
    assert (row.code, row.system) == ("default_invoice", True)
