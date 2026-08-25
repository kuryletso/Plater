"""Measurement units: user-added registry rows alongside the seeded ones."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.db.models.registries.measurement_unit_localization import (
    MeasurementUnitRegistryLocalization,
)
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.measurement_unit.repository import (
    MeasurementUnitRepository, MeasurementUnitText, normalize_code,
)


@pytest.fixture
def repo(session: Session) -> MeasurementUnitRepository:
    return MeasurementUnitRepository(session)


def create(repo, code="kilogram", name="Kilogram", *, name_ukr="Кілограм"):
    return repo.create(
        code,
        {
            "ENG": MeasurementUnitText(name=name),
            "UKR": MeasurementUnitText(name=name_ukr),
        },
    )


# --- code normalization ------------------------------------------------------

def test_the_code_is_normalized_because_lines_store_it():
    assert normalize_code("  Square Metre ") == "square_metre"
    assert normalize_code("HOUR") == "hour"


def test_create_stores_the_normalized_code(repo):
    created = create(repo, "  Square Metre ")

    assert created.code == "square_metre"


def test_a_user_unit_is_not_marked_system(repo):
    created = create(repo)

    assert created.system is False
    assert created.active is True


def test_create_stores_every_localization(repo):
    created = create(repo)

    assert created.localizations["ENG"].name == "Kilogram"
    assert created.localizations["UKR"].name == "Кілограм"


# --- rejection ---------------------------------------------------------------

def test_an_empty_code_is_rejected(repo):
    with pytest.raises(InvalidSelection):
        create(repo, "   ")


def test_a_duplicate_code_is_rejected(repo):
    create(repo, "kilogram")

    with pytest.raises(InvalidSelection):
        create(repo, "kilogram")


def test_a_duplicate_is_caught_after_normalization(repo):
    """'Square Metre' and 'square_metre' are the same unit."""
    create(repo, "square_metre")

    with pytest.raises(InvalidSelection):
        create(repo, "  Square Metre  ")


def test_clashing_with_a_seeded_unit_is_rejected(repo, session: Session):
    """conftest seeds 'hour'; the registry is one namespace."""
    with pytest.raises(InvalidSelection):
        create(repo, "HOUR")


def test_at_least_one_localization_is_required(repo):
    with pytest.raises(InvalidSelection):
        repo.create("kilogram", {})


def test_an_unknown_language_is_rejected(repo):
    with pytest.raises(EntityNotFound):
        repo.create("kilogram", {"FRA": MeasurementUnitText(name="Kilogramme")})


def test_a_rejected_unit_is_not_stored(repo, session: Session):
    with pytest.raises(EntityNotFound):
        repo.create("kilogram", {"FRA": MeasurementUnitText(name="Kilogramme")})

    assert session.get(MeasurementUnitRegistry, "kilogram") is None


# --- listing -----------------------------------------------------------------

def test_list_returns_active_units_in_code_order(repo, session: Session):
    create(repo, "kilogram")
    create(repo, "box", name="Box", name_ukr="Коробка")

    codes = [unit.code for unit in repo.list()]

    assert codes == sorted(codes)
    assert {"box", "hour", "kilogram"} <= set(codes)


def test_list_hides_inactive_units_unless_asked(repo, session: Session):
    session.add(MeasurementUnitRegistry(
        code="retired", active=False,
        localizations={
            "ENG": MeasurementUnitRegistryLocalization(language_code="ENG", name="Retired"),
        },
    ))
    session.commit()

    assert "retired" not in {unit.code for unit in repo.list()}
    assert "retired" in {unit.code for unit in repo.list(include_inactive=True)}


def test_search_matches_the_code(repo):
    create(repo, "kilogram")

    assert [unit.code for unit in repo.list(search="kilo")] == ["kilogram"]


def test_search_matches_a_localized_name(repo):
    create(repo, "kilogram")

    assert [unit.code for unit in repo.list(search="Kilogram")] == ["kilogram"]


def test_search_folds_cyrillic_case(repo):
    """casefold() in Python, since SQLite's lower() leaves Cyrillic alone."""
    create(repo, "kilogram")

    assert [unit.code for unit in repo.list(search="кілограм")] == ["kilogram"]
    assert [unit.code for unit in repo.list(search="КІЛОГРАМ")] == ["kilogram"]


def test_search_excludes_non_matches(repo):
    create(repo, "kilogram")

    assert repo.list(search="parsec") == []
