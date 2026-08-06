"""The singleton template-defaults row: creation, reading and validated updates."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.configs.default_template_config import DefaultTemplateConfig
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.settings import TemplateDefaultService


def rows(session: Session) -> list[DefaultTemplateConfig]:
    return list(session.scalars(select(DefaultTemplateConfig)).all())


# --- ensure ------------------------------------------------------------------

def test_ensure_creates_the_row_on_a_fresh_database(session: Session):
    service = TemplateDefaultService(session)

    created = service.ensure()

    assert len(rows(session)) == 1
    assert created.primary_language_code == service.DEFAULT_PRIMARY_LANGUAGE
    assert created.secondary_language_code == service.DEFAULT_SECONDARY_LANGUAGE
    assert created.document_type_code == service.DEFAULT_DOCUMENT_TYPE


def test_ensure_is_idempotent(session: Session):
    service = TemplateDefaultService(session)

    first = service.ensure()
    second = service.ensure()

    assert first.id == second.id
    assert len(rows(session)) == 1


def test_ensure_never_overwrites_user_choices(session: Session):
    """It runs on every launch, so it must not reset settings."""
    service = TemplateDefaultService(session)
    service.ensure()
    service.update(primary_language="UKR", secondary_language=None, append_currency=False)

    service.ensure()

    row = service.get()
    assert row.primary_language_code == "UKR"
    assert row.secondary_language_code is None, "a cleared secondary must stay cleared"
    assert row.append_currency is False


# --- get ---------------------------------------------------------------------

def test_get_returns_the_row(session: Session):
    service = TemplateDefaultService(session)
    created = service.ensure()

    assert service.get().id == created.id


def test_get_raises_before_initialisation(session: Session):
    with pytest.raises(EntityNotFound):
        TemplateDefaultService(session).get()


# --- update ------------------------------------------------------------------

def test_update_changes_only_what_was_passed(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()

    updated = service.update(name="Bilingual invoice")

    assert updated.name == "Bilingual invoice"
    assert updated.primary_language_code == service.DEFAULT_PRIMARY_LANGUAGE
    assert updated.document_type_code == service.DEFAULT_DOCUMENT_TYPE


def test_update_sets_a_secondary_language(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()

    updated = service.update(secondary_language="UKR")

    assert updated.secondary_language_code == "UKR"


def test_passing_none_clears_the_secondary_language(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()
    service.update(secondary_language="UKR")

    assert service.update(secondary_language=None).secondary_language_code is None


def test_omitting_the_secondary_language_leaves_it_alone(session: Session):
    """The sentinel default is what separates 'clear it' from 'do not touch it'."""
    service = TemplateDefaultService(session)
    service.ensure()
    service.update(secondary_language="UKR")

    assert service.update(name="unrelated").secondary_language_code == "UKR"


def test_update_rejects_an_unknown_language(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()

    with pytest.raises(EntityNotFound):
        service.update(primary_language="XXX")


def test_update_rejects_the_same_language_twice(session: Session):
    """A bilingual template with one language rendered twice is a user error."""
    service = TemplateDefaultService(session)
    service.ensure()

    with pytest.raises(InvalidSelection):
        service.update(primary_language="UKR", secondary_language="UKR")


def test_update_rejects_an_unknown_document_type(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()

    with pytest.raises(EntityNotFound):
        service.update(document_type="not_a_type")


def test_update_rejects_a_disabled_document_type(session: Session):
    service = TemplateDefaultService(session)
    service.ensure()
    session.add(DocumentTypeRegistry(code="retired", system=True, active=False))
    session.commit()

    with pytest.raises(InvalidSelection):
        service.update(document_type="retired")


def test_a_rejected_update_applies_nothing_at_all(session: Session):
    """Validation happens before mutation, so callers need no rollback."""
    service = TemplateDefaultService(session)
    service.ensure()

    with pytest.raises(EntityNotFound):
        service.update(name="should not stick", primary_language="XXX")

    assert service.get().name == "Invoice"


# --- the import provider reads it --------------------------------------------

def test_the_input_provider_uses_the_stored_defaults(session: Session):
    from app.services.template.db_input_provider import DbTemplateInputProvider

    service = TemplateDefaultService(session)
    service.ensure()
    service.update(primary_language="UKR", secondary_language="ENG",
                   append_currency=False)

    config = DbTemplateInputProvider(session).default_template_config()

    assert config.primary_language == "UKR"
    assert config.secondary_language == "ENG"
    assert config.append_currency is False
    assert DbTemplateInputProvider(session).languages() == {"UKR", "ENG"}
