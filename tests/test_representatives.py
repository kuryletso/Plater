"""Representative CRUD. They are shared between organizations, not owned by one."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core.representative import Representative
from app.db.models.core.representative_localization import RepresentativeLocalization
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.organization.repository import OrganizationRepository, OrganizationText
from app.services.representative.repository import (
    RepresentativeRepository, RepresentativeText,
)


def bilingual(name_en: str = "Ivan Petrenko", name_uk: str = "Іван Петренко"):
    return {
        "ENG": RepresentativeText(name=name_en, title="Director"),
        "UKR": RepresentativeText(name=name_uk, title="Директор"),
    }


def org_text(name: str = "Acme"):
    return {"ENG": OrganizationText(org_type="LLC", legal_name=name)}


@pytest.fixture
def repo(session: Session) -> RepresentativeRepository:
    return RepresentativeRepository(session)


@pytest.fixture
def organizations(session: Session) -> OrganizationRepository:
    return OrganizationRepository(session)


@pytest.fixture
def representative(repo):
    return repo.create(bilingual())


# --- create ------------------------------------------------------------------

def test_create_stores_every_localization(repo):
    created = repo.create(bilingual())

    stored = repo.get(created.id)
    assert set(stored.localizations) == {"ENG", "UKR"}
    assert stored.localizations["UKR"].name == "Іван Петренко"
    assert stored.localizations["ENG"].title == "Director"


def test_a_title_is_optional(repo):
    created = repo.create({"ENG": RepresentativeText(name="Ivan Petrenko")})

    assert repo.get(created.id).localizations["ENG"].title is None


def test_create_allows_a_single_language(repo):
    created = repo.create({"ENG": RepresentativeText(name="Ivan")})

    assert set(repo.get(created.id).localizations) == {"ENG"}


def test_create_rejects_no_localizations(repo):
    with pytest.raises(InvalidSelection):
        repo.create({})


def test_create_rejects_an_unknown_language(repo):
    with pytest.raises(EntityNotFound):
        repo.create({"XXX": RepresentativeText(name="Ivan")})


def test_a_new_representative_is_attached_to_nobody(repo, representative):
    assert repo.get(representative.id).organizations == []


# --- read --------------------------------------------------------------------

def test_get_raises_for_an_unknown_representative(repo):
    with pytest.raises(EntityNotFound):
        repo.get(9999)


def test_list_returns_everyone(repo):
    repo.create(bilingual("Ivan Petrenko", "Іван Петренко"))
    repo.create(bilingual("Olena Kovalenko", "Олена Коваленко"))

    assert len(repo.list()) == 2


def test_list_can_search_by_name(repo):
    repo.create(bilingual("Ivan Petrenko", "Іван Петренко"))
    repo.create(bilingual("Olena Kovalenko", "Олена Коваленко"))

    found = repo.list(search="kovalenko")

    assert [r.localizations["ENG"].name for r in found] == ["Olena Kovalenko"]


def test_search_matches_any_language(repo):
    repo.create(bilingual("Ivan Petrenko", "Іван Петренко"))
    repo.create(bilingual("Olena Kovalenko", "Олена Коваленко"))

    found = repo.list(search="Коваленко")

    assert [r.localizations["ENG"].name for r in found] == ["Olena Kovalenko"]


def test_list_can_be_narrowed_to_one_organization(repo, organizations):
    """The invoice draft picker only wants this organization's people."""
    acme = organizations.create(org_text("Acme"))
    globex = organizations.create(org_text("Globex"))

    ours = repo.create(bilingual("Ivan Petrenko", "Іван Петренко"))
    theirs = repo.create(bilingual("Olena Kovalenko", "Олена Коваленко"))

    organizations.attach_representative(acme.id, ours.id)
    organizations.attach_representative(globex.id, theirs.id)

    assert [r.id for r in repo.list(organization_id=acme.id)] == [ours.id]


# --- update ------------------------------------------------------------------

def test_update_changes_a_name_and_title(repo, representative, session: Session):
    representative_id = representative.id

    repo.update(representative_id, localizations={
        "ENG": RepresentativeText(name="Ivan Petrenko", title="Chief Executive"),
        "UKR": RepresentativeText(name="Іван Петренко", title="Директор"),
    })
    session.expunge_all()

    assert repo.get(representative_id).localizations["ENG"].title == "Chief Executive"


def test_update_replaces_the_whole_localization_set(repo, representative,
                                                    session: Session):
    """Dropping a language must actually delete the row."""
    representative_id = representative.id

    repo.update(representative_id, localizations={
        "ENG": RepresentativeText(name="Ivan Petrenko"),
    })
    session.expunge_all()

    assert set(repo.get(representative_id).localizations) == {"ENG"}
    assert len(session.scalars(select(RepresentativeLocalization)).all()) == 1


def test_update_can_clear_a_title(repo, representative, session: Session):
    representative_id = representative.id

    repo.update(representative_id, localizations={
        "ENG": RepresentativeText(name="Ivan Petrenko", title=None),
    })
    session.expunge_all()

    assert repo.get(representative_id).localizations["ENG"].title is None


def test_update_rejects_an_empty_localization_set(repo, representative):
    with pytest.raises(InvalidSelection):
        repo.update(representative.id, localizations={})


def test_update_without_arguments_is_a_no_op(repo, representative):
    unchanged = repo.update(representative.id)

    assert set(unchanged.localizations) == {"ENG", "UKR"}


def test_updating_does_not_disturb_attachments(repo, representative, organizations):
    acme = organizations.create(org_text("Acme"))
    organizations.attach_representative(acme.id, representative.id)

    repo.update(representative.id, localizations={
        "ENG": RepresentativeText(name="Ivan P."),
    })

    assert [o.id for o in repo.get(representative.id).organizations] == [acme.id]


# --- delete ------------------------------------------------------------------

def test_delete_removes_an_unattached_representative(repo, representative,
                                                     session: Session):
    repo.delete(representative.id)

    assert session.scalars(select(Representative)).all() == []
    assert session.scalars(select(RepresentativeLocalization)).all() == []


def test_delete_is_refused_while_still_attached(repo, representative, organizations):
    """Silently removing them from several organizations would be too surprising."""
    acme = organizations.create(org_text("Acme"))
    organizations.attach_representative(acme.id, representative.id)

    with pytest.raises(InvalidSelection):
        repo.delete(representative.id)

    assert repo.get(representative.id) is not None


def test_the_refusal_names_the_organizations(repo, representative, organizations):
    """So the GUI can say which ones rather than just refusing."""
    acme = organizations.create(org_text("Acme"))
    globex = organizations.create(org_text("Globex"))
    organizations.attach_representative(acme.id, representative.id)
    organizations.attach_representative(globex.id, representative.id)

    with pytest.raises(InvalidSelection) as excinfo:
        repo.delete(representative.id)

    assert set(excinfo.value.context["organization_ids"]) == {acme.id, globex.id}


def test_delete_succeeds_after_detaching(repo, representative, organizations,
                                         session: Session):
    acme = organizations.create(org_text("Acme"))
    organizations.attach_representative(acme.id, representative.id)
    organizations.detach_representative(acme.id, representative.id)

    repo.delete(representative.id)

    assert session.scalars(select(Representative)).all() == []


def test_deleting_an_organization_frees_its_representatives(repo, representative,
                                                            organizations):
    """The org owns the link, not the person — so the person becomes deletable."""
    acme = organizations.create(org_text("Acme"))
    organizations.attach_representative(acme.id, representative.id)

    organizations.delete(acme.id)
    repo.delete(representative.id)

    assert repo.list() == []


def test_delete_raises_for_an_unknown_representative(repo):
    with pytest.raises(EntityNotFound):
        repo.delete(9999)
