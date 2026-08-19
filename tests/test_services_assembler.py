"""Assembler: ORM entities -> InvoiceData, and the full assemble -> map -> RenderContext path."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.document_engine.blueprint.models.template import TemplateConfig
from app.services.invoice.assembler import (
    InvoiceAssembler,
    build_labels,
    money_format,
    resolve_languages,
    values_of,
)
from app.db.models.references.currency import Currency
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.db.models.registries.placeholder import PlaceholderRegistry
from app.db.models.registries.placeholder_localization import (
    PlaceholderRegistryLocalization,
)
from app.services.doc_sequence.repository import IssuedNumber, SequenceRepository
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.invoice.draft import InvoiceDraft, PartySelection
from app.services.invoice.mapper import InvoiceMapper
from app.services.language import LanguageSpec

from tests.conftest import CODES, LANGS


# assemble() takes the issued number from its caller; for tests that only
# exercise other fields, any plausible one will do.
NUMBER = IssuedNumber(prefix="INV-", number="0007")


def make_draft(provider_org, client_org, sequence, lines, **overrides) -> InvoiceDraft:
    kwargs = dict(
        template_id=1,
        sequence_id=sequence.id,
        currency_code="UAH",
        issue_date=date(2026, 7, 16),
        provider=PartySelection(
            organization_id=provider_org.id,
            tax_id_id=provider_org.tax_ids[0].id,
            representative_id=provider_org.representatives[0].id,
            bank_account_id=provider_org.bank_accounts[0].id,
        ),
        client=PartySelection(
            organization_id=client_org.id,
            tax_id_id=client_org.tax_ids[0].id,
        ),
        lines=lines,
    )
    kwargs.update(overrides)
    return InvoiceDraft(**kwargs)


@pytest.fixture
def assembler(session: Session) -> InvoiceAssembler:
    return InvoiceAssembler(session, LANGS)


@pytest.fixture
def invoice(session, make_org, make_line_input, make_sequence, assembler):
    """A fully assembled InvoiceData plus the entities behind it."""
    provider = make_org("Provider Co", tax_value="11111111")
    client = make_org("Client Co", tax_value="22222222")
    line = make_line_input()
    sequence = make_sequence(provider)

    draft = make_draft(provider, client, sequence, (line,))
    number = SequenceRepository(session).peek(sequence.id)
    return assembler.assemble(draft, number), provider, client, sequence, line


# --- helpers -----------------------------------------------------------------

def test_values_of_collects_requested_languages(session, make_org):
    org = make_org("Acme")
    assert values_of(org.localizations, "legal_name", CODES) == {
        "UKR": "Acme UA",
        "ENG": "Acme",
    }


def test_values_of_skips_absent_languages(session, make_org):
    org = make_org("Acme")
    assert values_of(org.localizations, "legal_name", ("ENG", "DEU")) == {"ENG": "Acme"}


def test_values_of_skips_null_attributes(session, make_org):
    org = make_org("Acme", with_bank=True)
    org.bank_accounts[0].localizations["ENG"].bank_info = None
    session.commit()

    assert values_of(org.bank_accounts[0].localizations, "bank_info", CODES) == {
        "UKR": "МФО 305299",
    }


def test_resolve_languages_pairs_iso3_with_alpha2(session):
    config = TemplateConfig(
        primary_language="UKR", secondary_language="ENG",
        type="invoice", name="t", description="", append_currency=True,
    )
    assert resolve_languages(session, config) == (
        LanguageSpec(code="UKR", alpha_2="uk"),
        LanguageSpec(code="ENG", alpha_2="en"),
    )


def test_resolve_languages_drops_absent_secondary(session):
    config = TemplateConfig(
        primary_language="ENG", secondary_language=None,
        type="invoice", name="t", description="", append_currency=False,
    )
    assert resolve_languages(session, config) == (LanguageSpec(code="ENG", alpha_2="en"),)


def test_resolve_languages_raises_for_unseeded_language(session):
    config = TemplateConfig(
        primary_language="XXX", secondary_language=None,
        type="invoice", name="t", description="", append_currency=False,
    )
    with pytest.raises(EntityNotFound):
        resolve_languages(session, config)


def test_money_format_reads_presets_and_localized_symbols(session):
    fmt = money_format(session.get(Currency, "UAH"), CODES)

    assert fmt.code == "UAH"
    assert fmt.decimal_separator == ","
    assert fmt.grouping_separator == " "
    assert fmt.symbols == {"UKR": "₴", "ENG": "UAH"}
    assert fmt.format(Decimal("1234.5"), "UKR", append=True) == "1 234,50 ₴"


def test_build_labels_returns_localized_table_headers(session):
    session.add(PlaceholderRegistry(
        key="invl_desc", required=True, type="COLUMN", active=True, columns=None,
        localizations={
            "UKR": PlaceholderRegistryLocalization(language_code="UKR", label="Опис"),
            "ENG": PlaceholderRegistryLocalization(language_code="ENG", label="Description"),
        },
    ))
    session.commit()

    assert build_labels(session, CODES)["invl_desc"] == {
        "UKR": "Опис",
        "ENG": "Description",
    }


def test_build_labels_omits_placeholders_without_labels(session):
    session.add(PlaceholderRegistry(
        key="total", required=True, type="SCALAR", active=True, columns=None,
    ))
    session.commit()

    assert "total" not in build_labels(session, CODES)


# --- assembly ----------------------------------------------------------------

def test_assemble_carries_the_issued_number(invoice):
    """The number is passed in, never derived: what the caller reserved is
    exactly what the document must say."""
    data, _, _, sequence, _ = invoice

    assert sequence.counter == 6
    assert data.number == "0007"      # peeked: counter + 1, zero-padded
    assert data.prefix == "INV-"


def test_a_prefixless_number_yields_an_empty_prefix(session, make_org, make_line_input,
                                                    make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    data = assembler.assemble(
        make_draft(provider, client, sequence, (line,)),
        IssuedNumber(prefix=None, number="001"),
    )

    assert data.prefix == ""
    assert data.number == "001"


def test_peek_and_assemble_do_not_consume_the_sequence(session, invoice):
    """Assembling is a read; a preview must not burn an invoice number."""
    _, _, _, sequence, _ = invoice
    session.refresh(sequence)

    assert sequence.counter == 6


def test_assemble_localizes_organization_fields(invoice):
    data, _, _, _, _ = invoice

    assert data.provider.legal_name == {"UKR": "Provider Co UA", "ENG": "Provider Co"}
    assert data.provider.address == {"UKR": "вул. Головна, 1", "ENG": "1 Main St"}
    assert data.provider.org_type == {"UKR": "ТОВ", "ENG": "LLC"}


def test_assemble_resolves_tax_id_with_system_and_country(invoice):
    data, _, _, _, _ = invoice

    assert data.provider.tax_id.value == "11111111"
    assert data.provider.tax_id.system == {"UKR": "ЄДРПОУ", "ENG": "EDRPOU"}
    assert data.provider.tax_id.country == {"UKR": "Україна", "ENG": "Ukraine"}


def test_assemble_includes_selected_representative_and_bank(invoice):
    data, _, _, _, _ = invoice

    assert data.provider.representative.name == {
        "UKR": "Іван Петренко", "ENG": "Ivan Petrenko",
    }
    assert data.provider.representative.title == {"UKR": "Директор", "ENG": "Director"}
    assert data.provider.bank.swift == "TESTUA00"
    assert data.provider.bank.bank_name == {"UKR": "ПриватБанк", "ENG": "PrivatBank"}


def test_unselected_representative_and_bank_are_none(invoice):
    """The client selection omits both ids."""
    data, _, _, _, _ = invoice

    assert data.client.representative is None
    assert data.client.bank is None


def test_representative_title_is_none_when_untranslated(session, make_org, make_line_input,
                                                        make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    for loc in provider.representatives[0].localizations.values():
        loc.title = None
    session.commit()

    line, sequence = make_line_input(), make_sequence(provider)
    data = assembler.assemble(make_draft(provider, client, sequence, (line,)), NUMBER)

    assert data.provider.representative.title is None


def test_assemble_maps_lines_with_localized_unit(invoice):
    data, _, _, _, _ = invoice
    (line,) = data.lines

    assert line.description == {"UKR": "Дизайн", "ENG": "Design work"}
    assert line.unit == {"UKR": "год", "ENG": "hr"}
    assert line.quantity == Decimal("10.000")
    assert line.unit_price == Decimal("125.50")
    assert line.tax_rate == Decimal("0.20000")


def test_lines_render_in_draft_order(session, make_org, make_line_input,
                                     make_sequence, assembler):
    """Row order is the user's, so the draft's tuple order is authoritative."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    sequence = make_sequence(provider)

    ordered = (make_line_input("Third"), make_line_input("First"), make_line_input("Second"))
    data = assembler.assemble(make_draft(provider, client, sequence, ordered), NUMBER)

    assert [line.description["ENG"] for line in data.lines] == ["Third", "First", "Second"]


def test_a_description_is_kept_only_for_rendered_languages(session, make_org,
                                                           make_line_input,
                                                           make_sequence, assembler):
    """A bilingual row rendered by a single-language template must not leak
    the other language into the context."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    sequence = make_sequence(provider)

    english_only = InvoiceAssembler(session, (LanguageSpec(code="ENG", alpha_2="en"),))
    data = english_only.assemble(
        make_draft(provider, client, sequence, (make_line_input(),)), NUMBER,
    )

    assert data.lines[0].description == {"ENG": "Design work"}


def test_an_empty_description_is_dropped_rather_than_rendered_blank(session, make_org,
                                                                    make_line_input,
                                                                    make_sequence,
                                                                    assembler):
    """The grid can leave the secondary description empty; that must read as
    'absent', not as an empty string."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    sequence = make_sequence(provider)

    line = make_line_input(description_ukr="")
    data = assembler.assemble(make_draft(provider, client, sequence, (line,)), NUMBER)

    assert data.lines[0].description == {"ENG": "Design work"}


def test_assemble_reads_currency_presets(invoice):
    data, _, _, _, _ = invoice

    assert data.currency.code == "UAH"
    assert data.currency.symbols == {"UKR": "₴", "ENG": "UAH"}


# --- failure modes -----------------------------------------------------------

def test_unknown_organization_raises_not_found(session, make_org, make_line_input,
                                               make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    draft = make_draft(
        provider, client, sequence, (line,),
        client=PartySelection(organization_id=9999, tax_id_id=1),
    )
    with pytest.raises(EntityNotFound):
        assembler.assemble(draft, NUMBER)


def test_unknown_measurement_unit_raises_not_found(session, make_org, make_line_input,
                                                   make_sequence, assembler):
    """Units are still registry-backed even though descriptions are free text."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    sequence = make_sequence(provider)

    line = make_line_input(unit="parsec")

    with pytest.raises(EntityNotFound):
        assembler.assemble(make_draft(provider, client, sequence, (line,)), NUMBER)


def test_a_disabled_unit_still_renders(session, make_org, make_line_input,
                                       make_sequence, assembler):
    """Regenerating an old invoice must not break because a unit was retired."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    sequence = make_sequence(provider)
    session.get(MeasurementUnitRegistry, "hour").active = False
    session.commit()

    data = assembler.assemble(
        make_draft(provider, client, sequence, (make_line_input(),)), NUMBER,
    )

    assert data.lines[0].unit == {"UKR": "год", "ENG": "hr"}


def test_unknown_currency_raises_not_found(session, make_org, make_line_input,
                                           make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    with pytest.raises(EntityNotFound):
        assembler.assemble(make_draft(provider, client, sequence, (line,),
                                      currency_code="XXX"),
                           NUMBER)


def test_tax_id_from_another_organization_is_rejected(session, make_org, make_line_input,
                                                      make_sequence, assembler):
    """A foreign tax id must not silently print on the invoice."""
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    draft = make_draft(
        provider, client, sequence, (line,),
        client=PartySelection(
            organization_id=client.id,
            tax_id_id=provider.tax_ids[0].id,
        ),
    )
    with pytest.raises(InvalidSelection):
        assembler.assemble(draft, NUMBER)


def test_bank_account_from_another_organization_is_rejected(session, make_org,
                                                            make_line_input,
                                                            make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    draft = make_draft(
        provider, client, sequence, (line,),
        client=PartySelection(
            organization_id=client.id,
            tax_id_id=client.tax_ids[0].id,
            bank_account_id=provider.bank_accounts[0].id,
        ),
    )
    with pytest.raises(InvalidSelection):
        assembler.assemble(draft, NUMBER)


def test_representative_from_another_organization_is_rejected(session, make_org,
                                                              make_line_input,
                                                              make_sequence, assembler):
    provider = make_org("P", tax_value="11111111")
    client = make_org("C", tax_value="22222222")
    line, sequence = make_line_input(), make_sequence(provider)

    draft = make_draft(
        provider, client, sequence, (line,),
        client=PartySelection(
            organization_id=client.id,
            tax_id_id=client.tax_ids[0].id,
            representative_id=provider.representatives[0].id,
        ),
    )
    with pytest.raises(InvalidSelection):
        assembler.assemble(draft, NUMBER)


# --- assemble -> map ---------------------------------------------------------

def test_assembled_invoice_maps_to_a_render_context(invoice):
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert context.scalars["date"] == {"UKR": "2026-07-16", "ENG": "2026-07-16"}
    assert context.scalars["prefix"] == {"UKR": "INV-", "ENG": "INV-"}
    assert context.scalars["id"] == {"UKR": "0007", "ENG": "0007"}
    assert context.scalars["curr"] == {"UKR": "UAH", "ENG": "UAH"}


def test_mapped_money_uses_localized_symbols(invoice):
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert context.scalars["subtotal"] == {"UKR": "1 255,00 ₴", "ENG": "1 255,00 UAH"}
    assert context.scalars["total_tax"] == {"UKR": "251,00 ₴", "ENG": "251,00 UAH"}
    assert context.scalars["total"] == {"UKR": "1 506,00 ₴", "ENG": "1 506,00 UAH"}


def test_total_text_is_spelled_in_ukrainian(invoice):
    """The end-to-end check that alpha-2 codes actually reach num2words."""
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert context.scalars["total_text"]["UKR"] == (
        "Одна тисяча п'ятсот шість гривень 00 копійок"
    )


def test_total_text_falls_back_to_the_iso_code(invoice):
    """num2words implements no UAH for English, so the ISO code names the currency."""
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert context.scalars["total_text"]["ENG"] == (
        "One thousand, five hundred and six UAH 00"
    )


def test_party_scalars_carry_the_role_prefix(invoice):
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert context.scalars["provider_name"]["ENG"] == "Provider Co"
    assert context.scalars["client_name"]["ENG"] == "Client Co"
    assert context.scalars["provider_tax_id"] == {"UKR": "11111111", "ENG": "11111111"}
    assert context.scalars["provider_country"]["ENG"] == "Ukraine"
    assert context.scalars["provider_bank_name"]["UKR"] == "ПриватБанк"


def test_absent_optional_values_are_not_emitted(invoice):
    """The client has no representative or bank; those keys must be missing entirely."""
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)

    assert "client_rep_name" not in context.scalars
    assert "client_iban" not in context.scalars
    assert "client_bank_name" not in context.scalars


def test_table_rows_carry_formatted_column_values(invoice):
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=True).map(data)
    (row,) = context.table.rows

    assert context.table.show_tax is True
    assert row.values["invl_n"] == {"UKR": "1", "ENG": "1"}
    assert row.values["invl_desc"]["UKR"] == "Дизайн"
    assert row.values["invl_qnty"] == {"UKR": "10", "ENG": "10"}
    assert row.values["invl_price"]["UKR"] == "125,50 ₴"
    assert row.values["invl_total"]["UKR"] == "1 255,00 ₴"


def test_append_currency_disabled_strips_symbols(invoice):
    data, _, _, _, _ = invoice
    context = InvoiceMapper(LANGS, labels={}, append_currency=False).map(data)

    assert context.scalars["total"] == {"UKR": "1 506,00", "ENG": "1 506,00"}
