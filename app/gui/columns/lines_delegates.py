from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QCompleter, QLineEdit, QStyledItemDelegate

from sqlalchemy.orm import Session

from app.services.invoice_line.repository import InvoiceLineRepository


class NumberDelegate(QStyledItemDelegate):
    """Text, not QDoubleSpinBox, for two reasons:
    1. empty cell must stay None rather than collapsing to 0;
    2. parsing Decimal straight from the typed string never inherits the binary float error Decimal(spin.value()) would.
    """

    def __init__(
            self,
            *,
            decimals: int,
            scale: Decimal = Decimal(1),
            parent=None,
    ) -> None:

        super().__init__(parent)
        self._decimals = decimals
        self._scale = scale


    def createEditor(self, parent, option, index) -> QLineEdit:
        editor = QLineEdit(parent)
        editor.setValidator(QRegularExpressionValidator(
            QRegularExpression(rf"\d{{0,12}}([,.]\d{{0,{self._decimals}}})?"),
            editor,
        ))
        return editor


    def setEditorData(self, editor, index) -> None:
        value = index.data(Qt.ItemDataRole.EditRole)
        editor.setText("" if value is None else f"{value * self._scale:g}")


    def setModelData(self, editor, model, index) -> None:
        text = editor.text().strip().replace(",", ".")
        if not text:
            model.setData(index, None, Qt.ItemDataRole.EditRole)
            return

        try:
            model.setData(index, Decimal(text) / self._scale, Qt.ItemDataRole.EditRole)
        except InvalidOperation:
            pass


class UnitDelegate(QStyledItemDelegate):
    def __init__(self, units: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._units = units     # (code, localized name)


    def createEditor(self, parent, option, index) -> QComboBox:
        editor = QComboBox(parent)
        for code, name in self._units:
            editor.addItem(name, code)
        return editor


    def setEditorData(self, editor, index) -> None:
        code = index.data(Qt.ItemDataRole.EditRole)
        editor.setCurrentIndex(editor.findData(code) if code else -1)


    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)


class DescriptionDelegate(QStyledItemDelegate):
    """Free text with frecency-ranked hints. Choosing one fills the whole row."""

    hint_chosen = Signal(int, int)

    def __init__(self, session: Session, language: str, parent=None) -> None:
        super().__init__(parent)
        self._repo = InvoiceLineRepository(session)
        self._language = language


    def createEditor(self, parent, option, index) -> QLineEdit:
        editor = QLineEdit(parent)
        position = index.row()

        completer = QCompleter(editor)
        # Unfiltered: hints() already filtered and ranked, and its casefold() handles Cyrillic (Qt's own matching does not)
        completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        model = QStandardItemModel(completer)
        completer.setModel(model)
        editor.setCompleter(completer)

        ids: dict[str, int] = {}

        def refresh(text: str) -> None:
            model.clear()
            ids.clear()
            for line in self._repo.hints(text or None):
                localization = line.localizations.get(self._language)
                if localization is None:
                    continue
                ids[localization.description] = line.id
                model.appendRow(QStandardItem(localization.description))

        def accept(text: str) -> None:
            line_id = ids.get(text)
            if line_id is not None:
                self.hint_chosen.emit(position, line_id)

        editor.textEdited.connect(refresh)
        completer.activated.connect(accept)
        refresh(editor.text())

        return editor


    def setEditorData(self, editor, index) -> None:
        editor.setText(index.data(Qt.ItemDataRole.EditRole) or "")


    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.text().strip(), Qt.ItemDataRole.EditRole)