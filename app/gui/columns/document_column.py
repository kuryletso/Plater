from __future__ import annotations

from decimal import Decimal
from datetime import date

from PySide6.QtCore import QDate, QSignalBlocker
from PySide6.QtWidgets import QWidget

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.references.currency import Currency
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.document_engine.rendering.validate import column_languages
from app.gui.columns.lines_row import LinesContainer
from app.gui.draft_state import DraftState
from app.gui.generated.ui_document_column import Ui_DocumentColumn
from app.gui.text import localized
from app.services.invoice.assembler import money_format
from app.services.invoice.totals import compute_totals
from app.services.template.repository import TemplateRepository


class DocumentColumn(QWidget):
    """Issue date, currency and invoice lines grid."""

    def __init__(
            self,
            session: Session,
            draft: DraftState,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._draft = draft
        self._languages: tuple[str, ...] = ()
        self.rendered: set[str] = set()
        self._blueprint_for: int | None = None

        self.ui = Ui_DocumentColumn()
        self.ui.setupUi(self)

        self._units = self._load_units()

        self.lines = LinesContainer(session)
        self.ui.lines_scroll.setWidget(self.lines)

        self.ui.add_button.clicked.connect(self.lines.add_row)
        self.lines.rows_changed.connect(self._push_rows)

        self.ui.date_edit.setDate(QDate.currentDate())
        self._populate_currencies()

        self.ui.date_edit.dateChanged.connect(self._on_date_changed)
        self.ui.currency_combo.currentIndexChanged.connect(self._on_currency_changed)
        draft.changed.connect(self._on_draft_changed)

        self._on_draft_changed()


    def _on_draft_changed(self) -> None:
        languages = self._grid_languages()

        if languages != self._languages:
            self._languages = languages
            self.lines.set_context(languages, self._units)

        ready = bool(languages)
        self.ui.lines_scroll.setEnabled(ready)
        self.ui.add_button.setEnabled(ready)
        self.ui.notice_label.setVisible(not ready)

        self._refresh_totals()


    def _grid_languages(self) -> tuple[str, ...]:
        """Languages the template actually renders descriptions in. 
        Declared secondary language it never places must not receive a column.
        """

        template_id = self._draft.template_id
        if template_id is None:
            return ()

        if template_id != self._blueprint_for:
            blueprint = TemplateRepository(self._session).get(template_id)
            self._rendered = column_languages(blueprint, "invl_desc")
            self._blueprint_for = template_id

        ordered = tuple( c for c in self._draft.languages if c in self._rendered )
        return ordered or self._draft.languages[:1]


    def _push_rows(self) -> None:
        self._draft.set_rows(self.lines.rows())

    def _on_date_changed(self, value: QDate) -> None:
        self._draft.set_issue_date( date(value.year(), value.month(), value.day()))

    def _on_currency_changed(self, position: int) -> None:
        self._draft.set_currency(
            self.ui.currency_combo.itemData(position) if position >= 0 else None
        )


    def _refresh_totals(self) -> None:
        """Same compute_total() and MoneyFormat the mapped uses so the strip can never disagree with the rendered document."""

        primary = self._languages[0] if self._languages else None
        currency = (
            self._session.get(Currency, self._draft.currency_code)
            if self._draft.currency_code else None
        )
        valid = [
            row for row in self.lines.rows()
            if primary and not row.is_blank() and not row.problems(primary)
        ]

        values = (
            self.ui.subtotal_value, self.ui.tax_value, self.ui.total_value,
        )
        if currency is None or primary is None or not valid:
            for label in values:
                label.setText("--")
            return

        fmt = money_format(currency, (primary,))
        totals = compute_totals(
            [ row.to_input() for row in valid],
            currency.decimal_places,
        )

        for label, amount in zip(
            values,
            (totals.subtotal, totals.total_tax, totals.total),
        ):
            label.setText(fmt.format(amount, primary, True))


    def _load_units(self) -> list[tuple[str, str]]:
        units = self._session.scalars(
            select(MeasurementUnitRegistry)
            .where(MeasurementUnitRegistry.active.is_(True))
            .order_by(MeasurementUnitRegistry.code)
        ).unique()

        return [ (unit.code, localized(unit.localizations, "name")) for unit in units]


    def _populate_currencies(self) -> None:
        combo = self.ui.currency_combo
        combo.setPlaceholderText("Select...")

        with QSignalBlocker(combo):
            for currency in self._session.scalars(
                select(Currency)
                .order_by(Currency.code)
            ).unique():
                combo.addItem(
                    f"{currency.code} — {localized(currency.localizations, 'name')}",
                    currency.code,
                )
            combo.setCurrentIndex(-1)