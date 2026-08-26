from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QTabWidget,
    QToolButton,
    QWidget,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.references.country import Country
from app.db.models.references.currency import Currency
from app.db.models.references.language import Language
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.db.models.configs.default_template_config import DefaultTemplateConfig
from app.gui.text import localized


def searchable_combo(
        items: Sequence[tuple[str, str, tuple[str, ...]]],
) -> ReferenceCombo:

    return ReferenceCombo(items)


def selected_code(combo: ReferenceCombo) -> str | None:
    return combo.code()


def show_code(combo: ReferenceCombo, code: str | None) -> None:
    combo.set_code(code)


def language_items(session: Session) -> list[tuple[str, str, tuple[str, ...]]]:
    return [
        (
            row.code,
            f"{row.label_en} ({row.code})",
            (row.label_en, row.label_uk, row.code_alpha_2),
        )
        for row in session.scalars(
            select(Language)
            .order_by(Language.label_en)
        )
    ]

def country_items(session: Session) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted(
        (
            (
                row.code,
                localized(row.localizations, "name"),
                _localized_names(row),
            )
            for row in session.scalars(select(Country)).unique()
        ),
        key=lambda item: item[1],
    )


def currency_items(session: Session) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted(
        (
            (
                row.code,
                f"{row.code} — {localized(row.localizations, 'name')}",
                _localized_names(row),
            )
            for row in session.scalars(select(Currency)).unique()
        ),
        key=lambda item: item[1],
    )


def tax_system_items(session: Session) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted(
        (
            (
                row.code,
                localized(row.localizations, "name"),
                _localized_names(row),
            )
            for row in session.scalars(
                select(TaxIdSystemRegistry)
                .where(TaxIdSystemRegistry.active.is_(True))
            ).unique()
        ),
        key=lambda item: item[1],
    )


def document_type_items(session: Session) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted(
        (
            (
                row.code,
                localized(row.localizations, "name"),
                _localized_names(row),
            )
            for row in session.scalars(
                select(DocumentTypeRegistry)
                .where(DocumentTypeRegistry.active.is_(True))
            ).unique()
        ),
        key=lambda item: item[1]
    )


def default_languages(session: Session) -> tuple[str, ...]:
    config = session.scalars(select(DefaultTemplateConfig)).first()
    if config is None:
        return ("ENG",)

    return tuple(
        code for code in (
            config.primary_language_code,
            config.secondary_language_code,
        ) if code
    )


def default_document_type(session: Session) -> str | None:
    config = session.scalars(select(DefaultTemplateConfig)).first()
    return config.document_type_code if config is not None else None


def _localized_names(row) -> tuple[str, ...]:
    return tuple(
        localization.name
        for localization in row.localizations.values()
        if localization.name
    )


class ErrorBanner(QLabel):
    """ServiceError's user_message lands here, inside a dialog, not in a second modal on top of it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setProperty("role", "error")
        self.hide()

    def show_message(self, message: str) -> None:
        self.setText(message)
        self.show()

    def clear_message(self) -> None:
        self.clear()
        self.hide()


class LocalizedFields(QWidget):
    """One tab per language, the same fields in each. Tabs open on demand."""

    def __init__(
            self,
            session: Session,
            fields: tuple[tuple[str, str], ...],     # (attribute, label)
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._fields = fields
        self._languages = language_items(session)
        self._names = { code: label for code, label, _ in self._languages}
        self._edits: dict[str, dict[str, QLineEdit]] = {}

        self.tabs = QTabWidget()

        add_button = QToolButton()
        add_button.setText("+")
        add_button.setAutoRaise(True)
        add_button.setToolTip("Add a language")
        add_button.clicked.connect(self._add_language)

        remove_button = QToolButton()
        remove_button.setText("−")
        remove_button.setAutoRaise(True)
        remove_button.setToolTip("Remove this language")
        remove_button.clicked.connect(self._remove_current)

        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0,0,0,0)
        corner_layout.addWidget(add_button)
        corner_layout.addWidget(remove_button)
        self.tabs.setCornerWidget(corner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.tabs)


    def set_values(self, values: dict[str, dict[str,str]]) -> None:
        while self.tabs.count():
            self.tabs.removeTab(0)
        self._edits.clear()

        for code, texts in values.items():
            self._add_tab(code)
            for attribute, edit in self._edits[code].items():
                edit.setText(texts.get(attribute) or "")


    def values(self) -> dict[str, dict[str, str]]:
        """Blank tabs are dropped."""

        out: dict[str, dict[str, str]] = {}
        for code, edits in self._edits.items():
            texts = {
                attribute: edit.text().strip()
                for attribute, edit in edits.items()
            }
            if any(texts.values()):
                out[code] = texts

        return out


    def _add_tab(self, code: str) -> None:
        page = QWidget()
        form = QFormLayout(page)
        edits: dict[str, QLineEdit] = {}

        for attribute, label in self._fields:
            edit = QLineEdit()
            form.addRow(label, edit)
            edits[attribute] = edit

        self._edits[code] = edits
        self.tabs.addTab(page, self._names.get(code, code))


    def _add_language(self) -> None:
        available = [
            (code, name)
            for code, name, _ in self._languages
            if code not in self._edits
        ]

        if not available:
            return

        name, accepted = QInputDialog.getItem(
            self, "Add a language", "Language:",
            [item[1] for item in available], 0, False,
        )
        if not accepted:
            return

        code = next( c for c,n in available if n == name )
        self._add_tab(code)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)


    def _remove_current(self) -> None:
        if self.tabs.count() <= 1:
            return

        position = self.tabs.currentIndex()
        code = list(self._edits)[position]
        del self._edits[code]
        self.tabs.removeTab(position)


    def language_name(self, code: str) -> str:
        return self._names.get(code, code)


class ReferenceCombo(QComboBox):
    """Editable, type-to-filter picker over a reference table.
    
    Typed text resolves against the code and every localized name, 
    not just displayed name. So the UI language does not affect user search.
    """

    def __init__(
            self,
            items: Sequence[tuple[str, str, tuple[str, ...]]],       # code, label, aliases
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._aliases: dict[str, str] = {}

        self.set_items(items)

        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(self._normalize)

    def set_items(
            self,
            items: Sequence[tuple[str, str, tuple[str, ...]]],
    ) -> None:
        """Repopulates in-place to keep current selection."""

        current = self.code()

        with QSignalBlocker(self):
            self.clear()
            self._aliases.clear()

            for code, label, aliases in items:
                self.addItem(label, code)
                for alias in aliases:
                    if alias:
                        self._aliases.setdefault(alias.casefold(), code)
                self._aliases[label.casefold()] = code
                self._aliases[code.casefold()] = code

        self._build_completer(items)
        self.set_code(current)


    def code(self) -> str | None:
        return self._aliases.get(self.currentText().strip().casefold())


    def set_code(self, code: str | None) -> None:
        self.setCurrentIndex(self.findData(code) if code else -1)


    def _build_completer(
            self,
            items: Sequence[tuple[str, str, tuple[str, ...]]],
    ) -> None:

        model = QStandardItemModel(self)
        seen: set[str] = set()

        for code, label, aliases in items:
            for text in (label, code, *aliases):
                key = text.casefold()
                if not text or key in seen:
                    continue

                seen.add(key)
                entry = QStandardItem(text)
                entry.setData(code, Qt.ItemDataRole.UserRole)
                model.appendRow(entry)

        completer = QCompleter(model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(completer)


    def _normalize(self) -> None:
        """Shows canonical label whatever user typed or picked."""

        code = self.code()
        if code is not None:
            self.set_code(code)