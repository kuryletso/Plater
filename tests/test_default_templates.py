"""Seeding of the shipped default templates."""

import json
import shutil

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core.assets import Asset
from app.db.models.core.template import Template
from app.db.models.core.template_version import TemplateVersion
from app.services.template import defaults as defaults_module
from app.services.template.defaults import seed_default_templates
from app.services.template.repository import TemplateRepository


@pytest.fixture
def shipped(tmp_path, monkeypatch, make_docx, session: Session, seeded_inputs):
    """Point the seeder at a throwaway manifest + template dir.

    Uses generated .docx files so the tests exercise the flow rather than the
    contents of the real shipped templates.
    """

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    manifest = tmp_path / "templates.json"

    def _install(entries: list[dict], sources: dict[str, list[str]]) -> None:
        for filename, paragraphs in sources.items():
            shutil.copy(make_docx(paragraphs=paragraphs, name=filename),
                        template_dir / filename)
        manifest.write_text(json.dumps(entries), encoding="utf-8")

    monkeypatch.setattr(defaults_module, "MANIFEST", manifest)
    monkeypatch.setattr(defaults_module, "TEMPLATE_DIR", template_dir)

    _install.dir = template_dir
    _install.manifest = manifest
    return _install


def entry(code: str, file: str, **overrides) -> dict:
    return {
        "code": code,
        "file": file,
        "type": "invoice",
        "primary_language": "ENG",
        "secondary_language": None,
        "name": f"Template {code}",
        "description": "",
        "append_currency": True,
    } | overrides


def actions(results) -> dict[str, str]:
    return {r.code: r.action for r in results}


# --- first run ---------------------------------------------------------------

def test_first_run_creates_every_shipped_template(session: Session, shipped):
    shipped(
        [entry("a", "a.docx"), entry("b", "b.docx")],
        {"a.docx": ["A {{ org_name }}"], "b.docx": ["B {{ org_name }}"]},
    )

    results = seed_default_templates(session)

    assert actions(results) == {"a": "created", "b": "created"}
    assert {t.code for t in session.scalars(select(Template)).all()} == {"a", "b"}


def test_seeded_templates_are_marked_system_and_named_from_the_manifest(session: Session,
                                                                        shipped):
    shipped([entry("a", "a.docx", name="Default invoice")],
            {"a.docx": ["A {{ org_name }}"]})

    seed_default_templates(session)

    template = session.scalars(select(Template)).one()
    assert template.system is True
    assert template.active is True
    assert template.name == "Default invoice"
    assert template.type == "invoice"


def test_seeded_template_starts_at_version_one_and_is_loadable(session: Session, shipped):
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})

    (result,) = seed_default_templates(session)

    repo = TemplateRepository(session)
    assert repo.current_version(result.template_id).version == 1
    assert "org_name" in repo.get(result.template_id).placeholders


# --- re-running --------------------------------------------------------------

def test_unchanged_templates_are_not_re_ingested(session: Session, shipped):
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})
    seed_default_templates(session)

    results = seed_default_templates(session)

    assert actions(results) == {"a": "unchanged"}
    assert len(session.scalars(select(TemplateVersion)).all()) == 1


def test_seeding_is_idempotent_across_many_runs(session: Session, shipped):
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})

    for _ in range(3):
        seed_default_templates(session)

    assert len(session.scalars(select(Template)).all()) == 1
    assert len(session.scalars(select(TemplateVersion)).all()) == 1


def test_a_changed_file_appends_a_new_version(session: Session, shipped, make_docx):
    """The shipped .docx changing is what drives a re-ingest."""
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})
    seed_default_templates(session)

    shutil.copy(make_docx(paragraphs=["A {{ org_name }} revised"], name="a.docx"),
                shipped.dir / "a.docx")
    results = seed_default_templates(session)

    assert actions(results) == {"a": "updated"}
    versions = session.scalars(
        select(TemplateVersion.version).order_by(TemplateVersion.version)
    ).all()
    assert list(versions) == [1, 2]


def test_an_updated_template_keeps_its_identity(session: Session, shipped, make_docx):
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})
    (first,) = seed_default_templates(session)

    shutil.copy(make_docx(paragraphs=["A {{ org_name }} revised"], name="a.docx"),
                shipped.dir / "a.docx")
    (second,) = seed_default_templates(session)

    assert second.template_id == first.template_id
    assert len(session.scalars(select(Template)).all()) == 1


def test_a_deactivated_default_is_not_resurrected(session: Session, shipped, make_docx):
    """Deleting a default means deleting it, even when a later release ships a new one."""
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})
    (created,) = seed_default_templates(session)

    session.get(Template, created.template_id).active = False
    session.commit()

    shutil.copy(make_docx(paragraphs=["A {{ org_name }} revised"], name="a.docx"),
                shipped.dir / "a.docx")
    results = seed_default_templates(session)

    assert actions(results) == {"a": "skipped"}
    assert len(session.scalars(select(TemplateVersion)).all()) == 1


# --- failure handling --------------------------------------------------------

def test_a_missing_file_is_reported_not_raised(session: Session, shipped):
    shipped([entry("a", "a.docx"), entry("gone", "missing.docx")],
            {"a.docx": ["A {{ org_name }}"]})

    results = seed_default_templates(session)

    assert actions(results) == {"a": "created", "gone": "failed"}


def test_one_broken_template_does_not_block_the_others(session: Session, shipped, tmp_path):
    """A malformed default must not stop the app from starting."""
    shipped([entry("broken", "broken.docx"), entry("ok", "ok.docx")],
            {"ok.docx": ["OK {{ org_name }}"]})
    (shipped.dir / "broken.docx").write_bytes(b"not a docx at all")

    results = seed_default_templates(session)

    assert actions(results) == {"broken": "failed", "ok": "created"}
    assert {t.code for t in session.scalars(select(Template)).all()} == {"ok"}


# --- assets ------------------------------------------------------------------

def test_the_source_docx_of_each_default_is_stored(session: Session, shipped):
    shipped([entry("a", "a.docx")], {"a.docx": ["A {{ org_name }}"]})

    (result,) = seed_default_templates(session)

    source = TemplateRepository(session).get_source(result.template_id)
    assert source.data == (shipped.dir / "a.docx").read_bytes()


def test_two_defaults_from_identical_files_share_one_stored_blob(session: Session, shipped):
    """Content addressing means duplicate shipped files cost one BLOB, not two."""
    shipped(
        [entry("a", "a.docx"), entry("b", "b.docx")],
        {"a.docx": ["Same {{ org_name }}"], "b.docx": ["Same {{ org_name }}"]},
    )

    seed_default_templates(session)

    assert len(session.scalars(select(Asset)).all()) == 1
