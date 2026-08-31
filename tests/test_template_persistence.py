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
from app.services.errors import EntityNotFound, InvalidSelection
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
    return pipeline.finalize(result.draft), result.assets, result.source


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
    return pipeline.finalize(result.draft), result.assets, result.source


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
    bp, bundle, source = ingested

    template_id = TemplateRepository(session).create(bp, bundle, source)

    row = session.get(Template, template_id)
    assert row.name == bp.config.name
    assert row.type == bp.config.type
    assert row.created_at is not None
    assert row.system is False
    assert row.active is True
    assert row.code is None


def test_create_records_a_system_template_under_its_code(session: Session, ingested):
    bp, bundle, source = ingested

    template_id = TemplateRepository(session).create(
        bp, bundle, source, code="default_invoice", system=True,
    )

    row = session.get(Template, template_id)
    assert row.code == "default_invoice"
    assert row.system is True


def test_create_starts_at_version_one_with_the_source_hash(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)

    assert versions_of(session, template_id) == [1]
    assert repo.current_version(template_id).source_sha256 == source.sha256


def test_saved_blueprint_round_trips_through_the_database(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)
    session.expunge_all()                       # force a real reload, not identity-map cache

    assert repo.get_blueprint(template_id) == bp


# --- list --------------------------------------------------------------------

def make_template(
    session: Session,
    name: str,
    *,
    type: str = "invoice",
    active: bool = True,
) -> Template:
    """list() reads only the templates table, so bare rows are enough."""
    row = Template(name=name, type=type, active=active)
    session.add(row)
    session.commit()
    return row


def test_list_returns_newest_first(session: Session):
    first = make_template(session, "Old")
    second = make_template(session, "New")

    assert [t.id for t in TemplateRepository(session).list()] == [second.id, first.id]


def test_list_search_matches_the_name_case_insensitively(session: Session):
    match = make_template(session, "Default Invoice")
    make_template(session, "Quote")

    found = TemplateRepository(session).list(search="invoice")

    assert [t.id for t in found] == [match.id]


def test_list_can_filter_by_document_type(session: Session):
    invoice = make_template(session, "Invoice", type="invoice")
    make_template(session, "Akt", type="akt")

    found = TemplateRepository(session).list(document_type="invoice")

    assert [t.id for t in found] == [invoice.id]


def test_list_hides_inactive_templates_unless_asked(session: Session):
    active = make_template(session, "Active")
    hidden = make_template(session, "Hidden", active=False)

    repo = TemplateRepository(session)

    assert [t.id for t in repo.list()] == [active.id]
    assert {t.id for t in repo.list(include_inactive=True)} == {active.id, hidden.id}


def test_create_persists_referenced_asset_blobs(session: Session, ingested):
    bp, bundle, source = ingested
    (asset_sha,) = collect_assets_ids(bp)

    TemplateRepository(session).create(bp, bundle, source)

    stored = session.get(Asset, asset_sha)
    assert stored.data == bundle[asset_sha].data
    assert stored.mime_type == "image/png"
    assert stored.size_bytes == len(bundle[asset_sha].data)


def test_assets_are_linked_to_the_version_not_the_template(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)

    links = links_of(session, repo.current_version(template_id).id)

    assert links == collect_assets_ids(bp) | {source.sha256}
    assert session.execute(select(template_version_asset_m2m)).all(), "linked at version level"


def test_create_ignores_bundle_entries_the_blueprint_does_not_reference(session: Session, ingested):
    """A parsed-but-dropped image must not leave an orphan BLOB behind."""
    bp, bundle, source = ingested
    padded = dict(bundle) | {
        "deadbeef": AssetBlob(sha256="deadbeef", mime_type="image/png", data=b"unused"),
    }

    TemplateRepository(session).create(bp, padded, source)

    assert session.get(Asset, "deadbeef") is None
    assert len(session.scalars(select(Asset)).all()) == 2      # the image + the source .docx


def test_two_templates_sharing_an_image_store_one_blob(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    repo.create(bp, bundle, source)
    repo.create(bp, bundle, source)

    assert len(session.scalars(select(Asset)).all()) == 2      # deduped image + source
    assert len(session.scalars(select(Template)).all()) == 2


# --- the source document -----------------------------------------------------

def test_the_source_docx_is_stored_alongside_the_images(session: Session, ingested):
    bp, bundle, source = ingested

    TemplateRepository(session).create(bp, bundle, source)

    stored = session.get(Asset, source.sha256)
    assert stored.data == source.data
    assert stored.mime_type.endswith("wordprocessingml.document")


def test_the_source_is_linked_to_the_version(session: Session, ingested):
    """Linked like any other asset, so the orphan sweep needs no special case."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)

    links = links_of(session, repo.current_version(template_id).id)
    assert links == collect_assets_ids(bp) | {source.sha256}


def test_get_source_returns_the_original_file(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)
    session.expunge_all()

    restored = repo.get_source(template_id)
    assert restored.data == source.data
    assert restored.sha256 == source.sha256


def test_get_source_can_fetch_an_older_version(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)

    template_id = repo.create(bp, bundle, source)
    repo.add_version(template_id, other_bp, other_bundle, other_source)

    assert repo.get_source(template_id, 1).sha256 == source.sha256
    assert repo.get_source(template_id).sha256 == other_source.sha256


def test_get_source_raises_for_an_unknown_version(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    with pytest.raises(EntityNotFound):
        repo.get_source(template_id, 99)


def test_deleting_a_template_collects_its_source_document(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    repo.delete(template_id)

    assert session.get(Asset, source.sha256) is None


def test_a_source_shared_by_two_templates_survives_the_first_delete(session: Session, ingested):
    """Two templates imported from the same file share one stored .docx."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    first, second = repo.create(bp, bundle, source), repo.create(bp, bundle, source)

    repo.delete(first)
    assert session.get(Asset, source.sha256) is not None

    repo.delete(second)
    assert session.get(Asset, source.sha256) is None


def test_get_raises_for_unknown_template(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).get_blueprint(9999)


def test_current_version_raises_when_there_are_none(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).current_version(9999)


# --- versions ----------------------------------------------------------------

def test_add_version_appends_and_returns_the_new_number(session: Session,
                                                        ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    version = repo.add_version(template_id, other_bp, other_bundle, other_source)

    assert version == 2
    assert versions_of(session, template_id) == [1, 2]


def test_get_returns_the_newest_version(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    repo.add_version(template_id, other_bp, other_bundle, other_source)
    session.expunge_all()

    assert repo.get_blueprint(template_id) == other_bp


def test_each_version_links_its_own_assets(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)
    first = repo.current_version(template_id).id

    repo.add_version(template_id, other_bp, other_bundle, other_source)
    second = repo.current_version(template_id).id

    assert links_of(session, first) == collect_assets_ids(bp) | {source.sha256}
    assert links_of(session, second) == collect_assets_ids(other_bp) | {other_source.sha256}
    assert links_of(session, first).isdisjoint(links_of(session, second))


def test_history_is_pruned_to_the_retention_limit(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    for _ in range(repo.KEEP_VERSIONS + 2):
        repo.add_version(template_id, bp, bundle, source)

    kept = versions_of(session, template_id)
    assert len(kept) == repo.KEEP_VERSIONS
    assert kept == sorted(kept)[-repo.KEEP_VERSIONS:]        # the newest survive


def test_pruning_drops_the_asset_links_of_removed_versions(session: Session,
                                                           ingested, other_ingested):
    """An image used only by a pruned version must not keep its BLOB alive."""
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)

    template_id = repo.create(other_bp, other_bundle, other_source)   # v1 uses the other image
    for _ in range(repo.KEEP_VERSIONS):
        repo.add_version(template_id, bp, bundle, source)             # push v1 out of retention

    (dropped_asset,) = collect_assets_ids(other_bp)
    (kept_asset,) = collect_assets_ids(bp)

    assert session.get(Asset, dropped_asset) is None
    assert session.get(Asset, kept_asset) is not None


def test_an_asset_shared_by_two_versions_survives_pruning_one(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)
    (asset_sha,) = collect_assets_ids(bp)

    for _ in range(repo.KEEP_VERSIONS + 1):
        repo.add_version(template_id, bp, bundle, source)

    assert session.get(Asset, asset_sha) is not None


def test_restore_copies_an_old_version_forward(session: Session, ingested, other_ingested):
    """History stays append-only: restoring v1 creates a new newest version."""
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)
    repo.add_version(template_id, other_bp, other_bundle, other_source)

    version = repo.restore(template_id, 1)
    session.expunge_all()

    assert version == 3
    assert versions_of(session, template_id) == [1, 2, 3]
    assert repo.get_blueprint(template_id) == bp


def test_restore_carries_the_original_source_hash(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)
    repo.add_version(template_id, other_bp, other_bundle, other_source)

    repo.restore(template_id, 1)

    assert repo.current_version(template_id).source_sha256 == source.sha256


def test_restore_raises_for_an_unknown_version(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    with pytest.raises(EntityNotFound):
        repo.restore(template_id, 99)


# --- copy --------------------------------------------------------------------

def test_copy_creates_an_editable_user_owned_template(session: Session, ingested):
    """Defaults are read-only; users work on a copy."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source, code="default_invoice", system=True)

    copy_id = repo.copy(origin, "My invoice")

    row = session.get(Template, copy_id)
    assert copy_id != origin
    assert row.name == "My invoice"
    assert row.system is False
    assert row.code is None
    assert row.type == session.get(Template, origin).type


def test_copy_starts_its_own_history_at_version_one(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)
    repo.add_version(origin, other_bp, other_bundle, other_source)

    copy_id = repo.copy(origin, "My invoice")

    assert versions_of(session, copy_id) == [1]
    assert versions_of(session, origin) == [1, 2]


def test_copy_takes_the_current_version_of_the_origin(session: Session,
                                                      ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)
    repo.add_version(origin, other_bp, other_bundle, other_source)

    copy_id = repo.copy(origin, "My invoice")
    session.expunge_all()

    copied = repo.get_blueprint(copy_id)                    # the newest, not the original v1
    assert copied.sections == other_bp.sections
    assert copied.placeholders == other_bp.placeholders


def test_copy_renames_the_config_to_match_the_template(session: Session, ingested):
    """Otherwise Template.name and blueprint.config.name disagree."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)

    copy_id = repo.copy(origin, "My invoice")
    session.expunge_all()

    assert repo.get_blueprint(copy_id).config.name == "My invoice"


def test_copy_shares_asset_blobs_rather_than_duplicating_them(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)
    before = len(session.scalars(select(Asset)).all())

    copy_id = repo.copy(origin, "My invoice")

    assert len(session.scalars(select(Asset)).all()) == before
    assert links_of(session, repo.current_version(copy_id).id) == \
        links_of(session, repo.current_version(origin).id)


def test_the_copy_can_restore_its_source_document(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)

    copy_id = repo.copy(origin, "My invoice")

    assert repo.get_source(copy_id).data == source.data


def test_deleting_the_origin_leaves_the_copy_intact(session: Session, ingested):
    """Reference counting: shared blobs survive while the copy still needs them."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source)
    copy_id = repo.copy(origin, "My invoice")

    repo.delete(origin)
    session.expunge_all()

    copied = repo.get_blueprint(copy_id)
    assert copied.sections == bp.sections          # only config.name is rewritten
    assert copied.placeholders == bp.placeholders
    assert repo.get_source(copy_id).data == source.data


def test_copy_raises_for_an_unknown_template(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateRepository(session).copy(9999, "My invoice")


# --- built-in templates are read-only ----------------------------------------

def test_a_built_in_template_cannot_be_edited(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    with pytest.raises(InvalidSelection):
        repo.add_version(template_id, other_bp, other_bundle, other_source)

    assert versions_of(session, template_id) == [1]


def test_a_built_in_template_cannot_be_rolled_back(session: Session, ingested):
    """restore() is editing too, so the same rule applies."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    with pytest.raises(InvalidSelection):
        repo.restore(template_id, 1)


def test_a_built_in_template_cannot_be_deleted(session: Session, ingested):
    """Otherwise 'delete' would silently mean 'reset to factory' on the next launch."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    with pytest.raises(InvalidSelection):
        repo.delete(template_id)

    assert session.get(Template, template_id) is not None


def test_a_built_in_template_can_be_hidden(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    repo.deactivate(template_id)
    assert session.get(Template, template_id).active is False

    repo.activate(template_id)
    assert session.get(Template, template_id).active is True


def test_a_built_in_template_can_still_be_copied(session: Session, ingested):
    """Copying is how users get an editable version — it must not be blocked."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    copy_id = repo.copy(template_id, "My invoice")

    assert session.get(Template, copy_id).system is False


def test_the_copy_of_a_built_in_is_editable(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    origin = repo.create(bp, bundle, source, code="default_invoice", system=True)
    copy_id = repo.copy(origin, "My invoice")

    assert repo.add_version(copy_id, other_bp, other_bundle, other_source) == 2


# --- the seeder's privileged path --------------------------------------------

def test_sync_updates_a_built_in_template(session: Session, ingested, other_ingested):
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source, code="default_invoice", system=True)

    version = repo.sync_system_version(template_id, other_bp, other_bundle, other_source)

    assert version == 2
    assert versions_of(session, template_id) == [1, 2]


def test_sync_refuses_a_user_template(session: Session, ingested, other_ingested):
    """The reverse guard: a seeder bug must not overwrite someone's own work."""
    bp, bundle, source = ingested
    other_bp, other_bundle, other_source = other_ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)          # user-owned, no code

    with pytest.raises(InvalidSelection):
        repo.sync_system_version(template_id, other_bp, other_bundle, other_source)

    assert versions_of(session, template_id) == [1]


# --- delete + asset GC -------------------------------------------------------

def test_delete_removes_the_template_its_versions_and_links(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    repo.delete(template_id)

    assert session.get(Template, template_id) is None
    assert versions_of(session, template_id) == []
    assert session.execute(select(template_version_asset_m2m)).all() == []


def test_delete_collects_the_now_orphaned_asset(session: Session, ingested):
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    template_id = repo.create(bp, bundle, source)

    repo.delete(template_id)

    assert session.scalars(select(Asset)).all() == []


def test_shared_asset_survives_until_its_last_template_is_deleted(session: Session, ingested):
    """The reference-counting rule: an asset dies only with its final referent."""
    bp, bundle, source = ingested
    repo = TemplateRepository(session)
    first, second = repo.create(bp, bundle, source), repo.create(bp, bundle, source)
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
    bp, bundle, source = ingested
    TemplateRepository(session).create(bp, bundle, source)
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

    assert result.source.sha256 == hash_bytes(path.read_bytes())


def test_commit_persists_the_reviewed_draft(session: Session, seeded_inputs,
                                            make_docx, make_png):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"], image=make_png())
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    template_id = service.commit(service.ingest(path))

    assert session.get(Template, template_id) is not None
    assert len(session.scalars(select(Asset)).all()) == 2      # the image + the source .docx
    assert "org_name" in TemplateRepository(session).get_blueprint(template_id).placeholders


def test_commit_can_mark_a_shipped_default(session: Session, seeded_inputs, make_docx):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    service = TemplateImportService(session, DbTemplateInputProvider(session))

    template_id = service.commit(service.ingest(path), code="default_invoice", system=True)

    row = session.get(Template, template_id)
    assert (row.code, row.system) == ("default_invoice", True)
