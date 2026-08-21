from __future__ import annotations

from typing import cast

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from app.gui.draft_state import LineRow
from app.gui.errors import MissingUIElement
from app.services.invoice_line.repository import InvoiceLineRepository
from app.db.models.core.invoice_line import InvoiceLine


def _decimal_edit(
        placeholder: str,
        decimals: int,
        width: int,
) -> QLineEdit:
    
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setFixedWidth(width)
    edit.setAlignment(Qt.AlignmentFlag.AlignRight)
    edit.setValidator(QRegularExpressionValidator(
        QRegularExpression(rf"\d{{0,12}}([.,]\d{{0,{decimals}}})?"),
        edit,
    ))
    return edit


def _parse(text: str) -> Decimal | None:
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


class LineRowWidget(QWidget):
    """One always-editable invoice line. Widgets write straight into the LineRow."""

    edited = Signal()
    remove_requested = Signal(object)
    move_requested= Signal(object, int)

    def __init__(
            self,
            row: LineRow,
            languages: tuple[str, ...],
            units: list[tuple[str,str]],        # (code, localized name)
            session: Session,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self.row = row
        self._languages = languages
        self._primary = languages[0] if languages else None
        self._repo = InvoiceLineRepository(session)

        self._unit_codes = { code.casefold(): code for code, _ in units }
        self._unit_codes.update({ name.casefold(): code for code, name in units })

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)

        self.number_label = QLabel("0.")
        self.number_label.setFixedWidth(22)
        self.number_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.number_label)

        named = len(languages) > 1
        self.description_edits: dict[str, QLineEdit] = {}
        for code in languages:
            edit = QLineEdit()
            edit.setPlaceholderText(f"Description ({code})" if named else "Description")
            edit.setText(row.descriptions.get(code, ""))
            edit.textEdited.connect(lambda text, c=code: self._on_description(c, text))
            layout.addWidget(edit, 3)
            self.description_edits[code] = edit

        if self._primary is not None:
            self._attach_completer(self.description_edits[self._primary])

        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.unit_combo.setMinimumWidth(90)
        for code, name in units:
            self.unit_combo.addItem(name, code)
        internal_line_edit = cast(QLineEdit, self.unit_combo.lineEdit())      # static checker fails to see self.unit_combo.setEditable(True) that prevents .lineEdit() from returning None
        internal_line_edit.setPlaceholderText("Unit")
        self._show_unit(row.unit_code)
        self.unit_combo.activated.connect(self._on_unit_picked)
        internal_line_edit.editingFinished.connect(self._on_unit_typed)
        layout.addWidget(self.unit_combo, 1)

        self.quantity_edit = _decimal_edit("Qty", 3, 55)
        self.price_edit = _decimal_edit("Price", 2, 70)
        self.tax_edit = _decimal_edit("Tax %", 2, 50)

        if row.quantity is not None:
            self.quantity_edit.setText(_plain(row.quantity))
        if row.unit_price is not None:
            self.price_edit.setText(_plain(row.unit_price))
        if row.tax_rate is not None:
            self.tax_edit.setText(_plain(row.tax_rate * 100))

        self.quantity_edit.textEdited.connect(self._on_numbers)
        self.price_edit.textEdited.connect(self._on_numbers)
        self.tax_edit.textEdited.connect(self._on_numbers)
        for edit in (self.quantity_edit, self.price_edit, self.tax_edit):
            layout.addWidget(edit)

        for text, slot, tooltip in (
            ("▲", lambda: self.move_requested.emit(self, -1), "Move up"),
            ("▼", lambda: self.move_requested.emit(self,  1), "Move down"),
            ("✕", lambda: self.remove_requested.emit(self), "Remove line"),
        ):
            button = QToolButton()
            button.setText(text)
            button.setAutoRaise(True)
            button.setToolTip(tooltip)
            button.clicked.connect(slot)
            layout.addWidget(button)

        self._refresh_warnings()

    def _on_description(self, code: str, text: str) -> None:
        self.row.descriptions[code] = text
        self._changed()


    def _on_unit_picked(self, position: int) -> None:
        self.row.unit_code = self.unit_combo.itemData(position)
        self._changed()


    def _on_unit_typed(self) -> None:
        """Typed text resolved against codes and localized names, casefolded.
        Should only be called after self.unit_combo.setEditable(True).
        """

        internal_line_edit = self.unit_combo.lineEdit()
        if internal_line_edit is None:
            raise MissingUIElement(
                "_on_unit_typed() is called before unit_combo.setEditable(True), "
                "unit_combo.lineEdit() returns None",
            )
        code = self._unit_codes.get(internal_line_edit.text().strip().casefold())
        if code != self.row.unit_code:
            self.row.unit_code = code
            self._show_unit(code)
            self._changed()


    def _on_numbers(self) -> None:
        self.row.quantity = _parse(self.quantity_edit.text())
        self.row.unit_price = _parse(self.price_edit.text())

        tax = _parse(self.tax_edit.text())
        self.row.tax_rate = tax / 100 if tax is not None else None
        self._changed()


    def _attach_completer(self, edit: QLineEdit) -> None:
        completer = QCompleter(edit)
        # Unfiltered because hints() already filtered and ranked, and its casefold()
        # handles Cyrillic better than Qt
        completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        model = QStandardItemModel(completer)
        completer.setModel(model)
        edit.setCompleter(completer)

        ids: dict[str, int] = {}

        def refresh(text: str) -> None:
            model.clear()
            ids.clear()
            for line in self._repo.hints(text or None):
                localization = line.localizations.get(self._primary or "")
                if localization is not None:
                    ids[localization.description] = line.id
                    model.appendRow(QStandardItem(localization.description))

        def accept(text: str) -> None:
            line_id = ids.get(text)
            if line_id is not None:
                self.fill_from(self._repo.get(line_id))

        edit.textEdited.connect(refresh)
        completer.activated.connect(accept)


    def fill_from(self, line: InvoiceLine) -> None:
        """Chosen hint fills everything except quantity, which is per-invoice."""

        self.row.descriptions.update({
            code: localization.description
            for code, localization in line.localizations.items()
        })

        self.row.unit_code = line.measurement_unit_code
        self.row.unit_price = line.unit_price
        self.row.tax_rate = line.tax_rate

        for code, edit in self.description_edits.items():
            edit.setText(self.row.descriptions.get(code, ""))
        self._show_unit(line.measurement_unit_code)
        self.price_edit.setText(_plain(line.unit_price))
        self.tax_edit.setText(_plain(line.tax_rate * 100))

        self._changed()


    def set_number(self, number: int) -> None:
        self.number_label.setText(f"{number}.")


    def _show_unit(self, code: str | None) -> None:
        self.unit_combo.setCurrentIndex(
            self.unit_combo.findData(code) if code else -1
        )


    def _refresh_warnings(self) -> None:
        """Empty secondary description on a started row prints black, warns but never blocks. 
        Full-rule QSS drives the tint (see main.py)."""

        for code, edit in self.description_edits.items():
            warn = (
                code != self._primary
                and not self.row.is_blank()
                and not self.row.descriptions.get(code, "").strip()
            )
            if bool(edit.property("warn")) != warn:
                edit.setProperty("warn", warn)
                edit.setToolTip(
                    f"Template renders {code} descriptions; "
                    f"this line will print blank."
                    if warn else ""
                )
                edit.style().unpolish(edit)
                edit.style().polish(edit)


    def _changed(self) -> None:
        self._refresh_warnings()
        self.edited.emit()


class LinesContainer(QWidget):

    rows_changed = Signal()

    def __init__(
            self,
            session: Session,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._languages: tuple[str, ...] = ()
        self._units: list[tuple[str, str]] = []
        self._rows: list[LineRow] = [LineRow()]
        self._widgets: list[LineRowWidget] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0,0,0,0)
        self._layout.addStretch(1)


    def set_context(
            self,
            languages: tuple[str, ...],
            units: list[tuple[str, str]],
    ) -> None:
        """Rebuild widgets if template changed; the LineRow data survives."""

        self._languages = languages
        self._units = units
        self._rebuild()


    def rows(self) -> tuple[LineRow, ...]:
        return tuple(self._rows)

    def add_row(self) -> None:
        self._rows.append(LineRow())
        self._insert_widget(self._rows[-1], len(self._widgets))
        self._renumber()
        self.rows_changed.emit()


    def _remove(self, widget: LineRowWidget) -> None:
        position = self._widgets.index(widget)
        del self._rows[position]
        self._widgets.pop(position)

        self._layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

        if not self._rows:
            self._rows.append(LineRow())
            self._insert_widget(self._rows[0], 0)

        self._renumber()
        self.rows_changed.emit()


    def _move(self, widget: LineRowWidget, delta: int) -> None:
        position = self._widgets.index(widget)
        target = position + delta
        if not 0 <= target < len(self._widgets):
            return

        self._rows.insert(target, self._rows.pop(position))
        self._widgets.insert(target, self._widgets.pop(position))
        self._layout.removeWidget(widget)
        self._layout.insertWidget(target, widget)

        self._renumber()
        self.rows_changed.emit()


    def _rebuild(self) -> None:
        for widget in self._widgets:
            self._layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._widgets.clear()

        for position, row in enumerate(self._rows):
            self._insert_widget(row, position)
        self._renumber()


    def _insert_widget(self, row: LineRow, position: int) -> None:
        widget = LineRowWidget(row, self._languages, self._units, self._session)
        widget.edited.connect(self.rows_changed)
        widget.remove_requested.connect(self._remove)
        widget.move_requested.connect(self._move)

        self._widgets.insert(position, widget)
        self._layout.insertWidget(position, widget)


    def _renumber(self) -> None:
        for position, widget in enumerate(self._widgets, start=1):
            widget.set_number(position)