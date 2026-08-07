"""Document sequences: numbering rules, and the peek/consume split that keeps
previews from burning invoice numbers."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core.document_sequence import DocumentSequence
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.organization.repository import OrganizationRepository, OrganizationText
from app.services.doc_sequence.repository import SequenceRepository


@pytest.fixture
def repo(session: Session) -> SequenceRepository:
    return SequenceRepository(session)


@pytest.fixture
def organization(session: Session):
    return OrganizationRepository(session).create(
        {"ENG": OrganizationText(org_type="LLC", legal_name="Acme")}
    )


@pytest.fixture
def sequence(repo, organization):
    return repo.create(organization.id, "invoice", prefix="INV-", counter=0, padding=5)


# --- create ------------------------------------------------------------------

def test_create_stores_the_numbering_rule(repo, organization):
    created = repo.create(organization.id, "invoice", prefix="INV-", padding=4)

    stored = repo.get(created.id)
    assert (stored.prefix, stored.counter, stored.padding) == ("INV-", 0, 4)
    assert stored.document_type_code == "invoice"


def test_a_prefix_is_optional(repo, organization):
    created = repo.create(organization.id, "invoice")

    assert repo.get(created.id).prefix is None


def test_a_blank_prefix_is_stored_as_none(repo, organization):
    """A GUI text field yields '', but the canonical 'no prefix' is None."""
    created = repo.create(organization.id, "invoice", prefix="")

    assert repo.get(created.id).prefix is None


def test_two_sequences_cannot_share_a_prefix(repo, organization):
    repo.create(organization.id, "invoice", prefix="INV-")

    with pytest.raises(InvalidSelection):
        repo.create(organization.id, "invoice", prefix="INV-")


def test_the_unprefixed_slot_is_also_exclusive(repo, organization):
    """SQLite treats NULLs as distinct, so only the explicit check stops a
    second unprefixed sequence issuing the same numbers."""
    repo.create(organization.id, "invoice", prefix=None)

    with pytest.raises(InvalidSelection):
        repo.create(organization.id, "invoice", prefix="")


def test_different_prefixes_coexist(repo, organization):
    repo.create(organization.id, "invoice", prefix="INV-")
    repo.create(organization.id, "invoice", prefix="PRO-")

    assert len(repo.list(organization_id=organization.id)) == 2


def test_the_same_prefix_may_serve_a_different_document_type(repo, organization,
                                                             session: Session):
    session.add(DocumentTypeRegistry(code="akt", system=True, active=True))
    session.commit()

    repo.create(organization.id, "invoice", prefix="X-")
    repo.create(organization.id, "akt", prefix="X-")

    assert len(repo.list(organization_id=organization.id)) == 2


def test_two_organizations_may_use_the_same_prefix(repo, organization, session: Session):
    other = OrganizationRepository(session).create(
        {"ENG": OrganizationText(org_type="LLC", legal_name="Globex")}
    )

    repo.create(organization.id, "invoice", prefix="INV-")
    repo.create(other.id, "invoice", prefix="INV-")

    assert len(repo.list()) == 2


def test_create_rejects_an_unknown_organization(repo):
    with pytest.raises(EntityNotFound):
        repo.create(9999, "invoice")


def test_create_rejects_a_disabled_document_type(repo, organization, session: Session):
    session.add(DocumentTypeRegistry(code="retired", system=True, active=False))
    session.commit()

    with pytest.raises(InvalidSelection):
        repo.create(organization.id, "retired")


def test_create_rejects_a_negative_counter(repo, organization):
    with pytest.raises(InvalidSelection):
        repo.create(organization.id, "invoice", counter=-1)


def test_a_migrated_sequence_can_start_partway(repo, organization):
    """Users arriving from another system continue their existing numbering."""
    created = repo.create(organization.id, "invoice", prefix="INV-",
                          counter=137, padding=4)

    assert repo.peek(created.id).formatted == "INV-0138"


# --- read --------------------------------------------------------------------

def test_get_raises_for_an_unknown_sequence(repo):
    with pytest.raises(EntityNotFound):
        repo.get(9999)


def test_list_can_filter_by_organization_and_type(repo, organization, session: Session):
    session.add(DocumentTypeRegistry(code="akt", system=True, active=True))
    session.commit()
    other = OrganizationRepository(session).create(
        {"ENG": OrganizationText(org_type="LLC", legal_name="Globex")}
    )

    repo.create(organization.id, "invoice", prefix="A-")
    repo.create(organization.id, "akt", prefix="B-")
    repo.create(other.id, "invoice", prefix="C-")

    assert len(repo.list(organization_id=organization.id)) == 2
    assert len(repo.list(document_type="invoice")) == 2
    assert len(repo.list(organization_id=organization.id, document_type="akt")) == 1


# --- numbering ---------------------------------------------------------------

def test_peek_reports_the_next_number_without_taking_it(repo, sequence):
    first = repo.peek(sequence.id)
    second = repo.peek(sequence.id)

    assert first.formatted == "INV-00001"
    assert second.formatted == "INV-00001"
    assert repo.get(sequence.id).counter == 0


def test_consume_issues_and_advances(repo, sequence):
    issued = repo.consume(sequence.id)

    assert issued.formatted == "INV-00001"
    assert repo.get(sequence.id).counter == 1


def test_consecutive_consumes_never_repeat(repo, sequence):
    issued = [repo.consume(sequence.id).formatted for _ in range(3)]

    assert issued == ["INV-00001", "INV-00002", "INV-00003"]


def test_peek_follows_the_last_consume(repo, sequence):
    repo.consume(sequence.id)
    repo.consume(sequence.id)

    assert repo.peek(sequence.id).formatted == "INV-00003"


def test_the_number_is_kept_apart_from_the_prefix(repo, sequence):
    """Templates place {{ prefix }} and {{ id }} separately."""
    issued = repo.consume(sequence.id)

    assert (issued.prefix, issued.number) == ("INV-", "00001")


def test_padding_of_zero_leaves_the_number_bare(repo, organization):
    created = repo.create(organization.id, "invoice", prefix="INV-", padding=0)

    assert repo.consume(created.id).formatted == "INV-1"


def test_a_number_longer_than_the_padding_is_not_truncated(repo, organization):
    created = repo.create(organization.id, "invoice", counter=9999, padding=2)

    assert repo.consume(created.id).number == "10000"


def test_an_unprefixed_sequence_yields_the_number_alone(repo, organization):
    created = repo.create(organization.id, "invoice", padding=3)
    issued = repo.consume(created.id)

    assert issued.prefix is None
    assert issued.formatted == "001"


# --- update ------------------------------------------------------------------

def test_update_changes_only_what_was_passed(repo, sequence):
    updated = repo.update(sequence.id, padding=3)

    assert updated.padding == 3
    assert updated.prefix == "INV-"
    assert updated.counter == 0


def test_the_counter_can_be_corrected(repo, sequence):
    """Migrating users adjust it to match the numbers they have already issued."""
    updated = repo.update(sequence.id, counter=250)

    assert repo.peek(updated.id).formatted == "INV-00251"


def test_update_rejects_a_negative_counter(repo, sequence):
    with pytest.raises(InvalidSelection):
        repo.update(sequence.id, counter=-5)


def test_update_rejects_a_prefix_already_in_use(repo, organization, sequence):
    repo.create(organization.id, "invoice", prefix="PRO-")

    with pytest.raises(InvalidSelection):
        repo.update(sequence.id, prefix="PRO-")


def test_keeping_its_own_prefix_is_not_a_clash(repo, sequence):
    updated = repo.update(sequence.id, prefix="INV-", padding=2)

    assert (updated.prefix, updated.padding) == ("INV-", 2)


# --- delete ------------------------------------------------------------------

def test_an_unused_sequence_can_be_deleted(repo, sequence, session: Session):
    repo.delete(sequence.id)

    assert session.scalars(select(DocumentSequence)).all() == []


def test_a_used_sequence_can_also_be_deleted(repo, sequence, session: Session):
    """Short-lived sequences are normal; only the counter is lost, and invoices
    are not stored, so users must not accumulate dead ones."""
    repo.consume(sequence.id)
    repo.consume(sequence.id)

    repo.delete(sequence.id)

    assert session.scalars(select(DocumentSequence)).all() == []


def test_deleting_frees_the_prefix_for_reuse(repo, organization, sequence):
    repo.consume(sequence.id)
    repo.delete(sequence.id)

    revived = repo.create(organization.id, "invoice", prefix="INV-", padding=5)

    assert repo.peek(revived.id).formatted == "INV-00001"


def test_delete_raises_for_an_unknown_sequence(repo):
    with pytest.raises(EntityNotFound):
        repo.delete(9999)
