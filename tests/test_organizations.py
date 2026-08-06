"""Organization CRUD: the organisation, its localizations, tax ids and bank accounts."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core.bank_account import BankAccount
from app.db.models.core.document_sequence import DocumentSequence
from app.db.models.core.organization import Organization
from app.db.models.core.representative import Representative
from app.db.models.core.representative_localization import RepresentativeLocalization
from app.db.models.core.tax_id import TaxId
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.organization.repository import (
    BankText, OrganizationRepository, OrganizationText,
)


def text(name: str = "Acme", org_type: str = "LLC", address: str | None = "1 Main St"):
    return OrganizationText(org_type=org_type, legal_name=name, address=address)


def bilingual(name_en: str = "Acme", name_uk: str = "Акме"):
    return {
        "ENG": OrganizationText(org_type="LLC", legal_name=name_en, address="1 Main St"),
        "UKR": OrganizationText(org_type="ТОВ", legal_name=name_uk, address="вул. Головна 1"),
    }


@pytest.fixture
def repo(session: Session) -> OrganizationRepository:
    return OrganizationRepository(session)


@pytest.fixture
def organization(repo):
    return repo.create(bilingual(), email="acme@example.com", phone="+380441234567")


# --- create ------------------------------------------------------------------

def test_create_stores_every_localization(repo, session: Session):
    organization = repo.create(bilingual())

    stored = repo.get(organization.id)
    assert set(stored.localizations) == {"ENG", "UKR"}
    assert stored.localizations["UKR"].legal_name == "Акме"
    assert stored.localizations["ENG"].org_type == "LLC"


def test_create_stores_contact_details(repo):
    organization = repo.create(bilingual(), email="a@b.com", phone="+380000000000")

    assert (organization.email, organization.phone) == ("a@b.com", "+380000000000")


def test_create_allows_a_single_language(repo):
    organization = repo.create({"ENG": text()})

    assert set(repo.get(organization.id).localizations) == {"ENG"}


def test_create_rejects_no_localizations(repo):
    with pytest.raises(InvalidSelection):
        repo.create({})


def test_create_rejects_an_unknown_language(repo):
    with pytest.raises(EntityNotFound):
        repo.create({"XXX": text()})


def test_an_address_is_optional(repo):
    organization = repo.create({"ENG": text(address=None)})

    assert repo.get(organization.id).localizations["ENG"].address is None


# --- read --------------------------------------------------------------------

def test_get_raises_for_an_unknown_organization(repo):
    with pytest.raises(EntityNotFound):
        repo.get(9999)


def test_list_returns_every_organization(repo):
    repo.create(bilingual("Acme", "Акме"))
    repo.create(bilingual("Globex", "Глобекс"))

    assert len(repo.list()) == 2


def test_list_can_search_by_localized_name(repo):
    repo.create(bilingual("Acme", "Акме"))
    repo.create(bilingual("Globex", "Глобекс"))

    found = repo.list(search="globex")

    assert [o.localizations["ENG"].legal_name for o in found] == ["Globex"]


def test_search_matches_any_language(repo):
    """A Ukrainian user searching Ukrainian names must find them."""
    repo.create(bilingual("Acme", "Акме"))
    repo.create(bilingual("Globex", "Глобекс"))

    found = repo.list(search="Глобекс")

    assert [o.localizations["ENG"].legal_name for o in found] == ["Globex"]


# --- update ------------------------------------------------------------------

def test_update_changes_only_what_was_passed(repo, organization):
    updated = repo.update(organization.id, email="new@example.com")

    assert updated.email == "new@example.com"
    assert updated.phone == "+380441234567"
    assert set(updated.localizations) == {"ENG", "UKR"}


def test_update_can_clear_contact_details(repo, organization):
    updated = repo.update(organization.id, email=None)

    assert updated.email is None


def test_update_replaces_the_whole_localization_set(repo, organization, session: Session):
    """Replacing lets a user drop a language, which merging could not express."""
    organization_id = organization.id                 # read it before detaching
    repo.update(organization_id, localizations={"ENG": text("Acme Renamed")})
    session.expunge_all()                             # force a reload, not the identity map

    stored = repo.get(organization_id)
    assert set(stored.localizations) == {"ENG"}
    assert stored.localizations["ENG"].legal_name == "Acme Renamed"


def test_update_rejects_an_empty_localization_set(repo, organization):
    with pytest.raises(InvalidSelection):
        repo.update(organization.id, localizations={})


def test_a_rejected_update_applies_nothing(repo, organization):
    with pytest.raises(EntityNotFound):
        repo.update(organization.id, email="kept@example.com",
                    localizations={"XXX": text()})

    assert repo.get(organization.id).email == "acme@example.com"


# --- tax ids -----------------------------------------------------------------

def test_add_tax_id(repo, organization):
    tax_id = repo.add_tax_id(
        organization.id, tax_id_system="ua_edrpou", country="UKR", value="12345678",
    )

    assert tax_id.value == "12345678"
    assert [t.id for t in repo.get(organization.id).tax_ids] == [tax_id.id]


def test_an_organization_can_hold_tax_ids_for_several_countries(repo, organization,
                                                                session: Session):
    session.add(TaxIdSystemRegistry(code="de_ust_id", system=True, active=True))
    session.commit()

    repo.add_tax_id(organization.id, tax_id_system="ua_edrpou",
                    country="UKR", value="12345678")
    repo.add_tax_id(organization.id, tax_id_system="de_ust_id",
                    country="UKR", value="DE999999")

    assert len(repo.get(organization.id).tax_ids) == 2


def test_the_same_system_and_country_cannot_repeat(repo, organization):
    repo.add_tax_id(organization.id, tax_id_system="ua_edrpou",
                    country="UKR", value="12345678")

    with pytest.raises(InvalidSelection):
        repo.add_tax_id(organization.id, tax_id_system="ua_edrpou",
                        country="UKR", value="87654321")


def test_add_tax_id_rejects_an_unknown_system(repo, organization):
    with pytest.raises(EntityNotFound):
        repo.add_tax_id(organization.id, tax_id_system="nope",
                        country="UKR", value="1")


def test_add_tax_id_rejects_a_disabled_system(repo, organization, session: Session):
    session.add(TaxIdSystemRegistry(code="retired", system=True, active=False))
    session.commit()

    with pytest.raises(InvalidSelection):
        repo.add_tax_id(organization.id, tax_id_system="retired",
                        country="UKR", value="1")


def test_remove_tax_id(repo, organization, session: Session):
    tax_id = repo.add_tax_id(organization.id, tax_id_system="ua_edrpou",
                             country="UKR", value="12345678")

    repo.remove_tax_id(organization.id, tax_id.id)

    assert repo.get(organization.id).tax_ids == []
    assert session.scalars(select(TaxId)).all() == []


def test_removing_a_tax_id_from_the_wrong_organization_is_refused(repo, organization):
    other = repo.create({"ENG": text("Globex")})
    tax_id = repo.add_tax_id(other.id, tax_id_system="ua_edrpou",
                             country="UKR", value="87654321")

    with pytest.raises(InvalidSelection):
        repo.remove_tax_id(organization.id, tax_id.id)


# --- bank accounts -----------------------------------------------------------

def test_add_bank_account_with_localizations(repo, organization):
    account = repo.add_bank_account(
        organization.id,
        iban="UA903052990000026007233566001",
        currency="UAH",
        country="UKR",
        swift="PBANUA2X",
        localizations={
            "ENG": BankText(bank_name="PrivatBank", bank_info="MFO 305299"),
            "UKR": BankText(bank_name="ПриватБанк", bank_info="МФО 305299"),
        },
    )

    stored = repo.get(organization.id).bank_accounts[0]
    assert stored.id == account.id
    assert stored.localizations["UKR"].bank_name == "ПриватБанк"
    assert stored.swift == "PBANUA2X"


def test_a_bank_account_needs_no_localizations(repo, organization):
    account = repo.add_bank_account(
        organization.id, iban="UA1", currency="UAH", country="UKR",
    )

    assert account.localizations == {}


def test_an_iban_cannot_be_reused(repo, organization):
    """IBAN is globally unique, so the clash may be with another organisation."""
    other = repo.create({"ENG": text("Globex")})
    repo.add_bank_account(other.id, iban="UA1", currency="UAH", country="UKR")

    with pytest.raises(InvalidSelection):
        repo.add_bank_account(organization.id, iban="UA1", currency="UAH", country="UKR")


def test_add_bank_account_rejects_an_unknown_currency(repo, organization):
    with pytest.raises(EntityNotFound):
        repo.add_bank_account(organization.id, iban="UA1", currency="XXX", country="UKR")


def test_remove_bank_account(repo, organization, session: Session):
    account = repo.add_bank_account(
        organization.id, iban="UA1", currency="UAH", country="UKR",
    )

    repo.remove_bank_account(organization.id, account.id)

    assert repo.get(organization.id).bank_accounts == []
    assert session.scalars(select(BankAccount)).all() == []


# --- representatives ---------------------------------------------------------

def make_representative(session: Session) -> Representative:
    representative = Representative(localizations={
        "ENG": RepresentativeLocalization(
            language_code="ENG", name="Ivan Petrenko", title="Director",
        ),
    })
    session.add(representative)
    session.commit()
    return representative


def test_attach_and_detach_a_representative(repo, organization, session: Session):
    representative = make_representative(session)

    repo.attach_representative(organization.id, representative.id)
    assert [r.id for r in repo.get(organization.id).representatives] == [representative.id]

    repo.detach_representative(organization.id, representative.id)
    assert repo.get(organization.id).representatives == []


def test_attaching_twice_is_harmless(repo, organization, session: Session):
    representative = make_representative(session)

    repo.attach_representative(organization.id, representative.id)
    repo.attach_representative(organization.id, representative.id)

    assert len(repo.get(organization.id).representatives) == 1


def test_a_representative_can_serve_two_organizations(repo, organization,
                                                      session: Session):
    """They are shared, not owned — detaching one must not affect the other."""
    representative = make_representative(session)
    other = repo.create({"ENG": text("Globex")})

    repo.attach_representative(organization.id, representative.id)
    repo.attach_representative(other.id, representative.id)
    repo.detach_representative(organization.id, representative.id)

    assert repo.get(organization.id).representatives == []
    assert [r.id for r in repo.get(other.id).representatives] == [representative.id]
    assert session.get(Representative, representative.id) is not None


def test_attach_rejects_an_unknown_representative(repo, organization):
    with pytest.raises(EntityNotFound):
        repo.attach_representative(organization.id, 9999)


# --- delete ------------------------------------------------------------------

def test_delete_removes_the_organization_and_what_it_owns(repo, organization,
                                                          session: Session):
    repo.add_tax_id(organization.id, tax_id_system="ua_edrpou",
                    country="UKR", value="12345678")
    repo.add_bank_account(organization.id, iban="UA1", currency="UAH", country="UKR")

    repo.delete(organization.id)

    assert session.scalars(select(Organization)).all() == []
    assert session.scalars(select(TaxId)).all() == []
    assert session.scalars(select(BankAccount)).all() == []


def test_delete_leaves_shared_representatives_alone(repo, organization,
                                                    session: Session):
    representative = make_representative(session)
    repo.attach_representative(organization.id, representative.id)

    repo.delete(organization.id)

    assert session.get(Representative, representative.id) is not None


def test_delete_is_refused_once_invoice_numbers_have_been_issued(repo, organization,
                                                                 session: Session):
    """Deleting would destroy the sequence and restart numbering at one."""
    session.add(DocumentSequence(
        document_type_code="invoice", organization_id=organization.id,
        prefix="INV-", counter=7, padding=4,
    ))
    session.commit()

    with pytest.raises(InvalidSelection):
        repo.delete(organization.id)

    assert repo.get(organization.id) is not None


def test_an_unused_sequence_does_not_block_deletion(repo, organization,
                                                    session: Session):
    session.add(DocumentSequence(
        document_type_code="invoice", organization_id=organization.id,
        prefix="INV-", counter=0, padding=4,
    ))
    session.commit()

    repo.delete(organization.id)

    assert session.scalars(select(DocumentSequence)).all() == []


def test_delete_raises_for_an_unknown_organization(repo):
    with pytest.raises(EntityNotFound):
        repo.delete(9999)
