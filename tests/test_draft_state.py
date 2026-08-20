"""DraftState: cascade rules, pristine -> complete -> invalid transitions, and
agreement between is_complete() and to_draft()."""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QCoreApplication

from app.gui.draft_state import (
    CLIENT, COLUMNS, DOCUMENT, PROVIDER, TEMPLATE, ColumnStatus, DraftState, LineRow,
)

LANGUAGES = ("ENG", "UKR")


def row(
    description: str = "Design work",
    *,
    description_ukr: str | None = "Дизайн",
    unit: str | None = "hour",
    quantity: str | None = "10",
    unit_price: str | None = "125.50",
    tax_rate: str | None = "0.2",
) -> LineRow:
    """A complete row by default; pass None to leave a cell untyped."""

    descriptions = {}
    if description is not None:
        descriptions["ENG"] = description
    if description_ukr is not None:
        descriptions["UKR"] = description_ukr

    return LineRow(
        descriptions=descriptions,
        unit_code=unit,
        quantity=Decimal(quantity) if quantity is not None else None,
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        tax_rate=Decimal(tax_rate) if tax_rate is not None else None,
    )


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Signals need a QCoreApplication; one per test session is enough."""
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def draft() -> DraftState:
    return DraftState()


def complete(draft: DraftState) -> DraftState:
    """Fill every required field (and no optional ones)."""
    draft.set_template(1, "invoice", LANGUAGES)
    draft.set_provider_organization(10)
    draft.set_provider_tax(11)
    draft.set_sequence(12)
    draft.set_client_organization(20)
    draft.set_client_tax(21)
    draft.set_rows((row(), row("Consulting")))
    draft.set_currency("UAH")
    return draft


# --- initial state -----------------------------------------------------------

def test_everything_starts_pristine(draft):
    assert set(draft.statuses().values()) == {ColumnStatus.PRISTINE}
    assert not draft.is_complete()


def test_issue_date_defaults_to_today(draft):
    assert draft.issue_date == date.today()
    assert all("date" not in gap.lower()
               for gaps in draft.missing_by_column().values() for gap in gaps)


def test_initial_gaps_name_every_column_but_none_twice(draft):
    missing = draft.missing_by_column()

    assert set(missing) == set(COLUMNS)
    assert missing[TEMPLATE] == ["Select a template"]


def test_tax_gap_appears_only_after_an_organization_is_chosen(draft):
    """'Select the tax ID' before an org is picked would be noise."""
    assert all("tax" not in gap.lower() for gap in draft.missing_by_column()[PROVIDER])

    draft.set_provider_organization(10)

    assert any("tax" in gap.lower() for gap in draft.missing_by_column()[PROVIDER])


# --- signals -----------------------------------------------------------------

def test_every_setter_emits_changed_exactly_once(draft):
    emissions = []
    draft.changed.connect(lambda: emissions.append(1))

    complete(draft)                     # 8 setter calls
    draft.set_issue_date(date(2026, 8, 1))
    draft.set_provider_bank(40)

    assert len(emissions) == 10


# --- cascades ----------------------------------------------------------------

def test_changing_document_type_clears_the_sequence(draft):
    complete(draft)

    draft.set_template(2, "akt", LANGUAGES)

    assert draft.sequence_id is None


def test_switching_templates_of_the_same_type_keeps_the_sequence(draft):
    """Comparing two invoice templates must not punish the user."""
    complete(draft)

    draft.set_template(2, "invoice", LANGUAGES)

    assert draft.sequence_id == 12


def test_changing_provider_org_clears_its_dependents_and_the_sequence(draft):
    complete(draft)
    draft.set_provider_representative(41)
    draft.set_provider_bank(42)

    draft.set_provider_organization(99)

    assert draft.provider_tax_id is None
    assert draft.provider_representative_id is None
    assert draft.provider_bank_id is None
    assert draft.sequence_id is None


def test_reasserting_the_same_provider_org_clears_nothing(draft):
    complete(draft)

    draft.set_provider_organization(10)

    assert draft.provider_tax_id == 11
    assert draft.sequence_id == 12


def test_changing_client_org_clears_only_client_fields(draft):
    complete(draft)
    draft.set_client_representative(43)

    draft.set_client_organization(99)

    assert draft.client_tax_id is None
    assert draft.client_representative_id is None
    assert draft.provider_tax_id == 11
    assert draft.sequence_id == 12


# --- status transitions ------------------------------------------------------

def test_a_column_completes_when_its_fields_are_filled(draft):
    draft.set_template(1, "invoice", LANGUAGES)

    statuses = draft.statuses()
    assert statuses[TEMPLATE] is ColumnStatus.COMPLETE
    assert statuses[PROVIDER] is ColumnStatus.PRISTINE


def test_a_regressed_column_turns_invalid_not_pristine(draft):
    complete(draft)

    draft.set_template(2, "akt", LANGUAGES)        # cascade empties the sequence

    assert draft.statuses()[PROVIDER] is ColumnStatus.INVALID


def test_unpicking_a_template_marks_it_invalid(draft):
    draft.set_template(1, "invoice", LANGUAGES)

    draft.set_template(None, None, ())

    assert draft.statuses()[TEMPLATE] is ColumnStatus.INVALID


def test_a_never_completed_column_stays_pristine_through_edits(draft):
    draft.set_provider_organization(10)

    assert draft.statuses()[PROVIDER] is ColumnStatus.PRISTINE

    draft.set_provider_organization(None)

    assert draft.statuses()[PROVIDER] is ColumnStatus.PRISTINE


def test_an_invalid_column_recovers_to_complete(draft):
    complete(draft)
    draft.set_template(2, "akt", LANGUAGES)

    draft.set_sequence(50)

    assert draft.statuses()[PROVIDER] is ColumnStatus.COMPLETE


# --- line rows ---------------------------------------------------------------

def test_an_untouched_row_is_blank():
    assert LineRow().is_blank()


def test_a_row_with_any_typed_cell_is_no_longer_blank():
    assert not LineRow(descriptions={"ENG": "x"}).is_blank()
    assert not LineRow(unit_code="hour").is_blank()
    assert not LineRow(quantity=Decimal("1")).is_blank()


def test_whitespace_alone_still_counts_as_blank():
    assert LineRow(descriptions={"ENG": "   "}).is_blank()


def test_a_complete_row_has_no_problems():
    assert row().problems("ENG") == []


def test_problems_name_each_missing_cell():
    assert row(quantity=None).problems("ENG") == ["quantity"]
    assert row(unit=None, unit_price=None).problems("ENG") == ["unit", "price"]


def test_a_zero_quantity_is_a_problem_but_a_zero_price_is_not():
    """Free-of-charge lines are legitimate; zero-quantity lines are not."""
    assert row(quantity="0").problems("ENG") == ["quantity"]
    assert row(unit_price="0").problems("ENG") == []


def test_missing_tax_is_never_a_problem():
    assert row(tax_rate=None).problems("ENG") == []


def test_only_the_primary_description_is_required():
    """A bilingual template warns about the empty secondary, never blocks on it."""
    assert row(description_ukr=None).problems("ENG") == []
    assert row(description=None).problems("ENG") == ["description"]


def test_to_input_defaults_missing_tax_to_zero():
    assert row(tax_rate=None).to_input().tax_rate == Decimal(0)


def test_to_input_strips_and_drops_empty_descriptions():
    built = row(description="  Design work  ", description_ukr="  ").to_input()

    assert built.descriptions == {"ENG": "Design work"}


# --- document column readiness -----------------------------------------------

def test_no_rows_at_all_asks_for_a_line(draft):
    draft.set_template(1, "invoice", LANGUAGES)

    assert "Add at least one invoice line" in draft.missing_by_column()[DOCUMENT]


def test_a_lone_blank_row_still_asks_for_a_line(draft):
    """The row we start with is workspace, not an invoice line."""
    draft.set_template(1, "invoice", LANGUAGES)
    draft.set_rows((LineRow(),))

    assert "Add at least one invoice line" in draft.missing_by_column()[DOCUMENT]


def test_blank_rows_alongside_a_valid_one_are_ignored(draft):
    complete(draft)
    draft.set_rows((row(), LineRow(), LineRow()))

    assert DOCUMENT not in draft.missing_by_column()


def test_a_half_typed_row_is_reported_with_its_grid_position(draft):
    complete(draft)
    draft.set_rows((row(), row("Consulting", quantity=None)))

    assert draft.missing_by_column()[DOCUMENT] == ["Line 2: quantity required"]


def test_row_numbering_counts_blank_rows_the_user_can_see(draft):
    complete(draft)
    draft.set_rows((row(), LineRow(), row("Consulting", unit=None)))

    assert draft.missing_by_column()[DOCUMENT] == ["Line 3: unit required"]


def test_several_gaps_in_one_row_are_named_together(draft):
    complete(draft)
    draft.set_rows((row(unit=None, quantity=None),))

    assert draft.missing_by_column()[DOCUMENT] == ["Line 1: unit and quantity required"]


def test_blank_rows_are_left_out_of_the_draft(draft):
    complete(draft)
    draft.set_rows((LineRow(), row(), LineRow()))

    assert draft.to_draft().lines == (row().to_input(),)


def test_rows_are_not_judged_before_a_template_is_chosen(draft):
    """Descriptions cannot be validated until we know the template's languages."""
    draft.set_rows((row(description=None, description_ukr=None),))

    gaps = draft.missing_by_column()[DOCUMENT]
    assert not any(gap.startswith("Line ") for gap in gaps)


def test_switching_templates_keeps_typed_descriptions(draft):
    """Switching back must not lose typing, so languages never clear rows."""
    complete(draft)

    draft.set_template(2, "akt", ("UKR",))

    assert draft.rows[0].descriptions["ENG"] == "Design work"


# --- to_draft ----------------------------------------------------------------

def test_a_complete_state_builds_the_draft(draft):
    complete(draft)
    draft.set_issue_date(date(2026, 8, 1))

    built = complete(draft).to_draft()

    assert built.template_id == 1
    assert built.sequence_id == 12
    assert built.currency_code == "UAH"
    assert built.issue_date == date(2026, 8, 1)
    assert built.provider.organization_id == 10
    assert built.provider.tax_id_id == 11
    assert built.client.organization_id == 20
    assert built.client.tax_id_id == 21
    assert built.lines == (row().to_input(), row("Consulting").to_input())


def test_optional_selections_pass_through(draft):
    complete(draft)

    assert draft.to_draft().provider.representative_id is None

    draft.set_provider_representative(41)
    draft.set_client_bank(42)
    built = draft.to_draft()

    assert built.provider.representative_id == 41
    assert built.client.bank_account_id == 42


def test_to_draft_refuses_an_incomplete_state(draft):
    with pytest.raises(AssertionError):
        draft.to_draft()


def test_to_draft_agrees_with_is_complete(draft):
    """The cast()s in to_draft() are safe only while these two never disagree."""
    steps = (
        lambda: draft.set_template(1, "invoice", LANGUAGES),
        lambda: draft.set_provider_organization(10),
        lambda: draft.set_provider_tax(11),
        lambda: draft.set_sequence(12),
        lambda: draft.set_client_organization(20),
        lambda: draft.set_client_tax(21),
        lambda: draft.set_rows((row(),)),
        lambda: draft.set_currency("UAH"),
    )

    for step in steps:
        builds = True
        try:
            draft.to_draft()
        except AssertionError:
            builds = False
        assert builds == draft.is_complete()
        step()

    assert draft.is_complete() and draft.to_draft() is not None
