from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.document_engine.rendering.context import (
    RenderContext, InvoiceTableData, InvoiceLineRow, Values,
)
from app.document_engine.rendering.resolve.invoice_table import (
    NUMBER, DESCRIPTION, UNIT, QUANTITY, PRICE, TAX, TOTAL,
)
from app.services.invoice.data import InvoiceData, Party, Line
from app.services.invoice.totals import compute_totals, InvoiceTotals, LineTotals
from app.services.invoice import vocabulary as v
from app.services.money import MoneyFormat, format_quantity
from app.services.language import LanguageSpec
from app.services.spell_total import spell_total


class InvoiceMapper:

    def __init__(
            self,
            languages: tuple[LanguageSpec, ...],
            labels: dict[str, Values],
            append_currency: bool,
    ) -> None:
        
        self._langs = languages
        self._codes = tuple(lang.code for lang in languages)
        self._labels = labels
        self._append = append_currency


    def map(
            self,
            data: InvoiceData,
    ) -> RenderContext:
        
        totals = compute_totals(data.lines, data.currency.decimal_places)
        return RenderContext(
            scalars=self._scalars(data, totals),
            table=self._table(data, totals),
        )


    def _same(self, value: str) -> Values:
        return { code: value for code in self._codes }
    

    def _money(
            self,
            fmt: MoneyFormat,
            amount,
    ) -> Values:
        
        return fmt.format_all(amount, self._codes, self._append)
    

    def _date(self, value: date) -> Values:
        return self._same(value.isoformat())
    

    def _scalars(
            self,
            data: InvoiceData,
            totals: InvoiceTotals,
    ) -> dict[str, Values]:
        
        fmt = data.currency
        scalars: dict[str, Values] = {
            v.DATE: self._date(data.issue_date),
            v.PREFIX: self._same(data.prefix),
            v.ID: self._same(str(data.number)),
            v.CURRENCY: self._same(fmt.code),
            v.SUBTOTAL: self._money(fmt, totals.subtotal),
            v.TOTAL: self._money(fmt, totals.total),
            v.TOTAL_TEXT: self._total_text(fmt, totals.total),
        }
        if totals.taxed:
            scalars[v.TOTAL_TAX] = self._money(fmt, totals.total_tax)

        scalars.update(self._party(v.PROVIDER, data.provider))
        scalars.update(self._party(v.CLIENT, data.client))

        return scalars
    

    def _party(
            self,
            role: str,
            party: Party,
    ) -> dict[str, Values]:
        
        out: dict[str, Values] = {
            v.party_key(role, v.NAME): party.legal_name,
            v.party_key(role, v.ADDRESS): party.address,
            v.party_key(role, v.TYPE): party.org_type,
            v.party_key(role, v.TAX_ID): self._same(party.tax_id.value),
            v.party_key(role, v.TAX_SYS): party.tax_id.system,
            v.party_key(role, v.COUNTRY): party.tax_id.country,
        }

        for field, value in ((v.EMAIL, party.email), (v.PHONE, party.phone)):
            if value:
                out[v.party_key(role, field)] = self._same(value)

        if party.representative is not None:
            out[v.party_key(role, v.REP_NAME)] = party.representative.name
            if party.representative.title is not None:
                out[v.party_key(role, v.REP_TITLE)] = party.representative.title

        if party.bank is not None:
            out[v.party_key(role, v.IBAN)] = self._same(party.bank.iban)
            out[v.party_key(role, v.BANK_NAME)] = party.bank.bank_name
            out[v.party_key(role, v.BANK_INFO)] = party.bank.bank_info
            if party.bank.swift:
                out[v.party_key(role, v.SWIFT)] = self._same(party.bank.swift)

        return out
    

    def _total_text(
            self,
            fmt: MoneyFormat,
            amount: Decimal,
    ) -> Values:
        return {
            lang.code: spell_total(amount, fmt, lang.alpha_2)
            for lang in self._langs
        }
    

    def _table(
            self,
            data: InvoiceData,
            totals: InvoiceTotals,
    ) -> InvoiceTableData:
        
        fmt = data.currency
        rows = tuple(
            InvoiceLineRow(values=self._row(n, line, line_totals, fmt))
            for n, (line, line_totals) in enumerate(zip(data.lines, totals.lines), start=1)
        )

        return InvoiceTableData(
            rows=rows,
            show_tax=totals.taxed,
            subtotal=self._money(fmt, totals.subtotal),
            total_tax=self._money(fmt, totals.total_tax) if totals.taxed else None,
            total=self._money(fmt, totals.total),
            labels=self._labels,
        )
    

    def _row(
            self,
            n: int,
            line: Line,
            totals: LineTotals,
            fmt: MoneyFormat,
    ) -> dict[str, Values]:
        
        values: dict[str, Values] = {
            NUMBER: self._same(str(n)),
            DESCRIPTION: line.description,
            UNIT: line.unit,
            QUANTITY: self._same(format_quantity(line.quantity, fmt)),
            PRICE: self._money(fmt, line.unit_price),
            TAX: self._money(fmt, totals.tax),      # always present ot avoid issues with mixed-tax incoices; InvoiceTableData.show_tax still decides whether the column appears
            TOTAL: self._money(fmt, totals.net),
        }

        if line.tax_rate > 0:
            values[TAX] = self._money(fmt, totals.tax)
        return values