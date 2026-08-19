"""Invoice lines: the hint cache behind the lines grid — CRUD, plus the
write-back (touch) and frecency ranking (hints) that feed autocomplete."""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core.invoice_line import InvoiceLine
from app.db.models.core.invoice_line_localization import InvoiceLineLocalization
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.invoice_line.repository import InvoiceLineRepository, InvoiceLineText


@pytest.fixture
def repo(session: Session) -> InvoiceLineRepository:
    return InvoiceLineRepository(session)


@pytest.fixture
def line(repo):
    return repo.create(
        {
            "ENG": InvoiceLineText(description="Design work"),
            "UKR": InvoiceLineText(description="Дизайн"),
        },
        quantity=Decimal("10"),
        measurement_unit="hour",
        unit_price=Decimal("125.50"),
        tax_rate=Decimal("0.2"),
    )


# --- create ------------------------------------------------------------------

def test_create_stores_amounts_and_unit(repo, line):
    stored = repo.get(line.id)

    assert stored.quantity == Decimal("10")
    assert stored.unit_price == Decimal("125.50")
    assert stored.tax_rate == Decimal("0.2")
    assert stored.measurement_unit_code == "hour"


def test_create_stores_every_localization(repo, line):
    stored = repo.get(line.id)

    assert stored.localizations["ENG"].description == "Design work"
    assert stored.localizations["UKR"].description == "Дизайн"


def test_one_language_is_enough(repo):
    created = repo.create(
        {"ENG": InvoiceLineText(description="Consulting")},
        quantity=Decimal("1"),
        measurement_unit="hour",
        unit_price=Decimal("500"),
        tax_rate=Decimal("0"),
    )

    assert set(repo.get(created.id).localizations) == {"ENG"}


def test_create_requires_at_least_one_localization(repo):
    with pytest.raises(InvalidSelection):
        repo.create(
            {},
            quantity=Decimal("1"),
            measurement_unit="hour",
            unit_price=Decimal("1"),
            tax_rate=Decimal("0"),
        )


def test_create_rejects_an_unknown_language(repo):
    with pytest.raises(EntityNotFound):
        repo.create(
            {"FRA": InvoiceLineText(description="Conception")},
            quantity=Decimal("1"),
            measurement_unit="hour",
            unit_price=Decimal("1"),
            tax_rate=Decimal("0"),
        )


def test_create_rejects_an_unknown_measurement_unit(repo):
    with pytest.raises(EntityNotFound):
        repo.create(
            {"ENG": InvoiceLineText(description="Design work")},
            quantity=Decimal("1"),
            measurement_unit="parsec",
            unit_price=Decimal("1"),
            tax_rate=Decimal("0"),
        )


def test_create_rejects_a_disabled_measurement_unit(repo, session: Session):
    session.add(MeasurementUnitRegistry(code="cubit", active=False))
    session.commit()

    with pytest.raises(InvalidSelection):
        repo.create(
            {"ENG": InvoiceLineText(description="Design work")},
            quantity=Decimal("1"),
            measurement_unit="cubit",
            unit_price=Decimal("1"),
            tax_rate=Decimal("0"),
        )


def test_create_rejects_a_zero_quantity(repo):
    with pytest.raises(InvalidSelection):
        repo.create(
            {"ENG": InvoiceLineText(description="Design work")},
            quantity=Decimal("0"),
            measurement_unit="hour",
            unit_price=Decimal("1"),
            tax_rate=Decimal("0"),
        )


def test_create_rejects_a_negative_unit_price(repo):
    with pytest.raises(InvalidSelection):
        repo.create(
            {"ENG": InvoiceLineText(description="Design work")},
            quantity=Decimal("1"),
            measurement_unit="hour",
            unit_price=Decimal("-0.01"),
            tax_rate=Decimal("0"),
        )


def test_a_free_of_charge_line_is_legitimate(repo):
    """Zero price is a real row ('delivery included'); zero quantity is not."""
    created = repo.create(
        {"ENG": InvoiceLineText(description="Delivery")},
        quantity=Decimal("1"),
        measurement_unit="hour",
        unit_price=Decimal("0"),
        tax_rate=Decimal("0"),
    )

    assert repo.get(created.id).unit_price == Decimal("0")


def test_create_rejects_a_negative_tax_rate(repo):
    with pytest.raises(InvalidSelection):
        repo.create(
            {"ENG": InvoiceLineText(description="Design work")},
            quantity=Decimal("1"),
            measurement_unit="hour",
            unit_price=Decimal("1"),
            tax_rate=Decimal("-0.2"),
        )


def test_fractional_quantities_survive_the_round_trip(repo):
    """QUANTITY is Numeric(12,3); a GUI spinner will happily produce 2.505."""
    created = repo.create(
        {"ENG": InvoiceLineText(description="Design work")},
        quantity=Decimal("2.505"),
        measurement_unit="hour",
        unit_price=Decimal("99.99"),
        tax_rate=Decimal("0.07"),
    )

    stored = repo.get(created.id)
    assert stored.quantity == Decimal("2.505")
    assert stored.tax_rate == Decimal("0.07")


# --- read --------------------------------------------------------------------

def test_get_raises_for_an_unknown_line(repo):
    with pytest.raises(EntityNotFound):
        repo.get(9999)


def test_list_returns_newest_first(repo):
    first = repo.create(
        {"ENG": InvoiceLineText(description="First")},
        quantity=Decimal("1"), measurement_unit="hour",
        unit_price=Decimal("1"), tax_rate=Decimal("0"),
    )
    second = repo.create(
        {"ENG": InvoiceLineText(description="Second")},
        quantity=Decimal("1"), measurement_unit="hour",
        unit_price=Decimal("1"), tax_rate=Decimal("0"),
    )

    assert [l.id for l in repo.list()] == [second.id, first.id]


def test_search_matches_any_localized_description(repo, line):
    """A user typing in either language must find the same row.

    Case-insensitivity is ASCII-only: SQLite's lower()/LIKE do not fold
    Cyrillic, so 'дизайн' would miss 'Дизайн'. Shared limitation of every
    icontains search in the codebase, noted for the GUI stage.
    """
    assert [l.id for l in repo.list(search="design")] == [line.id]
    assert [l.id for l in repo.list(search="Дизайн")] == [line.id]
    assert repo.list(search="plumbing") == []


# --- update ------------------------------------------------------------------

def test_update_changes_only_what_was_passed(repo, line):
    updated = repo.update(line.id, unit_price=Decimal("150"))

    assert updated.unit_price == Decimal("150")
    assert updated.quantity == Decimal("10")
    assert updated.tax_rate == Decimal("0.2")
    assert updated.localizations["ENG"].description == "Design work"


def test_the_measurement_unit_can_be_changed(repo, line, session: Session):
    session.add(MeasurementUnitRegistry(code="piece"))
    session.commit()

    updated = repo.update(line.id, measurement_unit="piece")

    assert updated.measurement_unit_code == "piece"


def test_update_rejects_an_unknown_measurement_unit(repo, line):
    with pytest.raises(EntityNotFound):
        repo.update(line.id, measurement_unit="parsec")


def test_update_rejects_a_disabled_measurement_unit(repo, line, session: Session):
    session.add(MeasurementUnitRegistry(code="cubit", active=False))
    session.commit()

    with pytest.raises(InvalidSelection):
        repo.update(line.id, measurement_unit="cubit")


def test_disabling_a_unit_does_not_freeze_existing_lines(repo, line, session: Session):
    """Only *selecting* a disabled unit is blocked; a line already using one
    stays editable, or deactivation would strand rows."""
    session.get(MeasurementUnitRegistry, "hour").active = False
    session.commit()

    updated = repo.update(line.id, unit_price=Decimal("200"))

    assert updated.unit_price == Decimal("200")
    assert updated.measurement_unit_code == "hour"


def test_update_rejects_a_zero_quantity(repo, line):
    with pytest.raises(InvalidSelection):
        repo.update(line.id, quantity=Decimal("0"))


def test_update_rejects_a_negative_unit_price(repo, line):
    with pytest.raises(InvalidSelection):
        repo.update(line.id, unit_price=Decimal("-1"))


def test_update_rejects_a_negative_tax_rate(repo, line):
    with pytest.raises(InvalidSelection):
        repo.update(line.id, tax_rate=Decimal("-0.01"))


def test_a_failed_update_changes_nothing(repo, line):
    """Validation runs before any field is written, so a bad value in one
    field must not leak the good ones through."""
    with pytest.raises(InvalidSelection):
        repo.update(line.id, unit_price=Decimal("200"), quantity=Decimal("-1"))

    stored = repo.get(line.id)
    assert stored.unit_price == Decimal("125.50")
    assert stored.quantity == Decimal("10")


def test_update_edits_and_adds_localizations(repo, line, session: Session):
    from app.db.models.references.language import Language

    session.add(Language(code="POL", code_alpha_2="pl",
                         label_en="Polish", label_uk="Польська"))
    session.commit()

    updated = repo.update(line.id, localizations={
        "ENG": InvoiceLineText(description="Design & branding"),
        "UKR": InvoiceLineText(description="Дизайн"),
        "POL": InvoiceLineText(description="Projektowanie"),
    })

    assert updated.localizations["ENG"].description == "Design & branding"
    assert updated.localizations["POL"].description == "Projektowanie"


def test_languages_left_out_of_an_update_are_removed(repo, line, session: Session):
    repo.update(line.id, localizations={
        "ENG": InvoiceLineText(description="Design work"),
    })

    assert set(repo.get(line.id).localizations) == {"ENG"}
    assert session.scalars(
        select(InvoiceLineLocalization)
        .where(InvoiceLineLocalization.language_code == "UKR")
    ).all() == []


def test_update_cannot_remove_the_last_localization(repo, line):
    with pytest.raises(InvalidSelection):
        repo.update(line.id, localizations={})


def test_update_raises_for_an_unknown_line(repo):
    with pytest.raises(EntityNotFound):
        repo.update(9999, unit_price=Decimal("1"))


# --- delete ------------------------------------------------------------------

def test_delete_removes_the_line_and_its_localizations(repo, line, session: Session):
    repo.delete(line.id)

    assert session.scalars(select(InvoiceLine)).all() == []
    assert session.scalars(select(InvoiceLineLocalization)).all() == []


def test_delete_raises_for_an_unknown_line(repo):
    with pytest.raises(EntityNotFound):
        repo.delete(9999)


# --- touch: cache write-back after a successful generate ----------------------

def touch(repo, description="Design work", *, description_ukr="Дизайн",
          quantity="10", unit="hour", unit_price="125.50", tax_rate="0.2"):
    return repo.touch(
        {
            "ENG": InvoiceLineText(description=description),
            "UKR": InvoiceLineText(description=description_ukr),
        },
        quantity=Decimal(quantity),
        measurement_unit=unit,
        unit_price=Decimal(unit_price),
        tax_rate=Decimal(tax_rate),
    )


def test_touching_an_unseen_line_stores_it(repo, session: Session):
    stored = touch(repo)

    assert session.scalars(select(InvoiceLine)).unique().all() == [stored]
    assert stored.use_count == 1


def test_touching_a_known_line_bumps_it_instead_of_duplicating(repo, session: Session):
    first = touch(repo)
    second = touch(repo)

    assert second.id == first.id
    assert second.use_count == 2
    assert len(session.scalars(select(InvoiceLine)).unique().all()) == 1


def test_matching_ignores_case(repo):
    """The user retyping 'design work' must not fork the hint."""
    first = touch(repo, "Design work")
    second = touch(repo, "DESIGN WORK")

    assert second.id == first.id


def test_quantity_is_remembered_but_never_matched(repo):
    """Quantity is per-invoice; billing 40 hours instead of 10 is the same line."""
    first = touch(repo, quantity="10")
    second = touch(repo, quantity="40")

    assert second.id == first.id
    assert second.quantity == Decimal("40")


def test_a_new_price_forks_a_new_hint(repo, session: Session):
    """Price changes are real, so both survive and the stale one decays away."""
    first = touch(repo, unit_price="125.50")
    second = touch(repo, unit_price="150.00")

    assert second.id != first.id
    assert len(session.scalars(select(InvoiceLine)).unique().all()) == 2


def test_a_different_description_forks_a_new_hint(repo):
    assert touch(repo, "Design work").id != touch(repo, "Consulting").id


def test_dropping_a_language_forks_a_new_hint(repo):
    """Descriptions must match as a whole, not per language."""
    both = touch(repo)
    english_only = repo.touch(
        {"ENG": InvoiceLineText(description="Design work")},
        quantity=Decimal("10"), measurement_unit="hour",
        unit_price=Decimal("125.50"), tax_rate=Decimal("0.2"),
    )

    assert english_only.id != both.id


# --- hints: frecency ranking --------------------------------------------------

def age(line, *, days: float, uses: int) -> None:
    line.last_used_at = datetime.now(UTC) - timedelta(days=days)
    line.use_count = uses


def test_hints_match_either_language(repo):
    line = touch(repo)

    assert [h.id for h in repo.hints("design")] == [line.id]
    assert [h.id for h in repo.hints("дизайн")] == [line.id]


def test_hint_search_folds_cyrillic_case(repo):
    """casefold() in Python is why this works where SQLite's lower() would not."""
    line = touch(repo, description_ukr="Дизайн")

    assert [h.id for h in repo.hints("ДИЗАЙН")] == [line.id]
    assert [h.id for h in repo.hints("дизайн")] == [line.id]


def test_hints_exclude_non_matches(repo):
    touch(repo, "Design work")

    assert repo.hints("plumbing") == []


def test_a_frequent_line_outranks_a_merely_recent_one(repo, session: Session):
    """The point of frecency: something billed monthly beats yesterday's one-off."""
    frequent = touch(repo, "Monthly retainer")
    once = touch(repo, "One-off fix")
    age(frequent, days=20, uses=12)
    age(once, days=0, uses=1)
    session.commit()

    assert [h.id for h in repo.hints()] == [frequent.id, once.id]


def test_recency_breaks_ties_between_equally_used_lines(repo, session: Session):
    stale = touch(repo, "Stale")
    fresh = touch(repo, "Fresh")
    age(stale, days=90, uses=3)
    age(fresh, days=1, uses=3)
    session.commit()

    assert [h.id for h in repo.hints()] == [fresh.id, stale.id]


def test_a_long_unused_line_decays_below_a_new_one(repo, session: Session):
    """Half-life is 30 days, so 8 uses a year ago must lose to 1 use today."""
    ancient = touch(repo, "Ancient")
    recent = touch(repo, "Recent")
    age(ancient, days=365, uses=8)
    age(recent, days=0, uses=1)
    session.commit()

    assert [h.id for h in repo.hints()] == [recent.id, ancient.id]


def test_hints_respect_the_limit(repo):
    for i in range(5):
        touch(repo, f"Line {i}")

    assert len(repo.hints(limit=3)) == 3
