from __future__ import annotations

import functools
from datetime import date
from collections.abc import Sequence, Iterable

from PySide6.QtCore import QPersistentModelIndex, Qt, QSignalBlocker, QCollator, QModelIndex
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
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
from app.gui.text import localized, preferred_languages, tax_system_label
from app.gui.icons import icon
from app.services.dates import DATE_FORMATS, DEFAULT_DATE_FORMAT, format_document_date

type Item = tuple[str, str, tuple[str, ...]]        # code, label, aliases


def searchable_combo(
        items: Sequence[tuple[str, str, tuple[str, ...]]],
) -> ReferenceCombo:

    return ReferenceCombo(items)


def selected_code(combo: ReferenceCombo) -> str | None:
    return combo.code()


def show_code(combo: ReferenceCombo, code: str | None) -> None:
    combo.set_code(code)


def language_items(session: Session) -> list[Item]:
    """Language named in the interface. The language table only carries English and Ukrainian names."""

    ukrainian = preferred_languages()[0] == "UKR"
    return _by_label(
        (
            row.code,
            f"{row.label_uk if ukrainian and row.label_uk else row.label_en} ({row.code})",
            (row.label_en, row.label_uk, row.code_alpha_2),
        ) for row in session.scalars(select(Language))
    )


def country_items(session: Session) -> list[Item]:
    return _by_label(
        (
            row.code,
            localized(row.localizations, "name"),
            _localized_names(row),
        ) for row in session.scalars(select(Country)).unique()
    )


def currency_items(session: Session) -> list[Item]:
    return _by_label(
        (
            row.code,
            f"{row.code} — {localized(row.localizations, 'name')}",
            _localized_names(row),
        ) for row in session.scalars(select(Currency)).unique()
    )


def tax_system_items(session: Session) -> list[Item]:
    """Labeled for the interface. Typing either label or name still finds a system."""

    return _by_label(
        (
            row.code,
            tax_system_label(row),
            (*_localized_names(row), *(label for label in (row.label_en, row.label_uk) if label)),
        ) for row in session.scalars(
            select(TaxIdSystemRegistry)
            .where(TaxIdSystemRegistry.active.is_(True))
        ).unique()
    )


def document_type_items(session: Session) -> list[Item]:
    return _by_label(
        (
            row.code,
            localized(row.localizations, 'name'),
            _localized_names(row),
        ) for row in session.scalars(
            select(DocumentTypeRegistry)
            .where(DocumentTypeRegistry.active.is_(True))
        ).unique()
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


def document_type_name(session: Session, code: str | None) -> str:
    """The name in the interface language if present, otherwise code."""

    row = session.get(DocumentTypeRegistry, code) if code else None
    if row is None or not row.localizations:
        return code or "?"
    return localized(row.localizations, "name")


def default_date_format(session: Session) -> str:
    config = session.scalars(select(DefaultTemplateConfig)).first()
    return config.date_format if config is not None else DEFAULT_DATE_FORMAT


def _localized_names(row) -> tuple[str, ...]:
    return tuple(
        localization.name
        for localization in row.localizations.values()
        if localization.name
    )


def _by_label(items: Iterable[Item]) -> list[Item]:
    """Alphabetical order in the interface langauge. Python orders by Unicode index, thus 
    Ukrainian І, Ї, Є, Ґ are misordered.
    """

    order = functools.cmp_to_key(QCollator().compare)
    return sorted(items, key=lambda item: order(item[1]))


class DateFormatCombo(QComboBox):
    """The date formats available to template. Each shown as an example."""

    EXAMPLE = date(2026, 5, 24)
    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        language = session.get(Language, preferred_languages()[0])
        interface = language.code_alpha_2 if language is not None else "en"

        notes = {
            "MM/dd/y": self.tr("{example} (US)"),
            "MMMM d, y": self.tr("{example} (US, English documents only)"),
        }
        for pattern in DATE_FORMATS:
            # the English-only format is shown in English as it will print
            locale = "en" if pattern == "MMMM d, y" else interface
            example = format_document_date(self.EXAMPLE, pattern, locale)
            self.addItem(
                notes[pattern].format(example=example) if pattern in notes else example,
                pattern,
            )

    def pattern(self) -> str:
        return self.currentData() or DEFAULT_DATE_FORMAT


    def set_pattern(self, pattern: str | None) -> None:
        """An unknown pattern falls back to the default."""

        position = self.findData(pattern or DEFAULT_DATE_FORMAT)
        self.setCurrentIndex(max(position, 0))


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
        add_button.setIcon(icon("plus"))
        add_button.setAutoRaise(True)
        add_button.setToolTip(self.tr("Add a language"))
        add_button.clicked.connect(self._add_language)

        remove_button = QToolButton()
        remove_button.setIcon(icon("minus"))
        remove_button.setAutoRaise(True)
        remove_button.setToolTip(self.tr("Remove this language"))
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
            self, self.tr("Add a language"), self.tr("Language:"),
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


_SEARCH_ROLE = Qt.ItemDataRole.UserRole + 1
class _LabelCompleter(QCompleter):
    """Matches an item by any of its names, then writes its label into the field."""

    def pathFromIndex(self, index: QModelIndex | QPersistentModelIndex) -> str:
        return index.data(Qt.ItemDataRole.DisplayRole)


class ReferenceCombo(QComboBox):
    """Editable on-typing filter picker over a reference table.
    
    Typed text resolved against the code and every localized name so the UI language does not limit 
    what a user can search for. 
    
    The popup lists every item once, by its label. `list_names` lists every name instead.
    """

    def __init__(
            self,
            items: Sequence[tuple[str, str, tuple[str, ...]]],      # code, label, aliases
            parent: QWidget | None = None,
            *,
            list_names: bool = False,
    ) -> None:

        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._list_names = list_names
        self._aliases: dict[str, str] = {}

        self.set_items(items)

        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(self._normalize)


    def set_items(
            self,
            items: Sequence[tuple[str, str, tuple[str, ...]]],
    ) -> None:
        """Repopulates in-place to keep current slection."""

        current = self.code()

        with QSignalBlocker(self):
            self.clear()
            for code, label, _ in items:
                self.addItem(label, code)

        self._aliases = _lookup(items)
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

        if self._list_names:
            seen: set[str] = set()
            for code, label, aliases in items:
                for text in (label, code, *aliases):
                    if not text or text.casefold() in seen:
                        continue

                    seen.add(text.casefold())
                    entry = QStandardItem(text)
                    entry.setData(code, Qt.ItemDataRole.UserRole)
                    model.appendRow(entry)

            completer = QCompleter(model, self)

        else:
            for code, label, aliases in items:
                entry = QStandardItem(label)
                entry.setData(code, Qt.ItemDataRole.UserRole)
                # one name per line
                entry.setData("\n".join(text for text in (label, code, *aliases) if text), _SEARCH_ROLE)
                model.appendRow(entry)

            completer = _LabelCompleter(model, self)
            completer.setCompletionRole(_SEARCH_ROLE)

        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(completer)


    def _normalize(self) -> None:
        """Shows canonical label whatever user typed or picked."""

        code = self.code()
        if code is not None:
            self.set_code(code)


def _lookup(items: Sequence[tuple[str, str, tuple[str, ...]]]) -> dict[str, str]:
    """Determines what typed text selects. A label or code always select its item. Matching name is 
    only selected if exactly one item has it.
    """

    owners: dict[str, set[str]] = {}
    for code, _, aliases in items:
        for alias in aliases:
            if alias:
                owners.setdefault(alias.casefold(), set()).add(code)

    lookup = { name: next(iter(codes)) for name, codes in owners.items() if len(codes) == 1 }
    for code, label, _ in items:
        lookup[label.casefold()] = code
        lookup[code.casefold()] = code

    return lookup