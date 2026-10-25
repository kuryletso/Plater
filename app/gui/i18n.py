"""The interface language: Qt's translators, installed once at startup.

Changing language takes effect on restart. Every widget is built in the language 
loaded when the window opened, nothing re-translates itself.

GUI code translates with self.tr() in a QObject, or QCoreApplication.translate() elsewhere. 
Errors and diagnostics are written outside the GUI and translated here, when they're 
shown (see app/core/messages.py).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from app.core.diagnostics import Diagnostic
from app.core.errors import AppError, Severity
from app.core.messages import CONTEXT, fill

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"

# English is the source language. Each of the following needs app/gui/translations/plater_<locale>.qm
LOCALES = {"UKR": "uk_UA"}

log = logging.getLogger("plater.i18n")

_installed: list[QTranslator] = []


def install(
        app: QCoreApplication,
        code: str,
        directory: Path = TRANSLATIONS_DIR,
) -> bool:
    """Load Plater's and Qt's own translations for the interface language `code` before 
    any widget is built. False if Plater's ones are missing: the interface stays in English, 
    mentioned in log.
    """

    uninstall()

    name = LOCALES.get(code)
    if name is None:
        _install_english(app, directory)
        return True

    locale = QLocale(name)

    plater = QTranslator(app)
    if not plater.load(locale, "plater", "_", str(directory)):
        log.warning("No compiled translation for %s; run scripts/build_ui.py", code)
        return False

    qt = QTranslator(app)
    if qt.load(locale, "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        _add(app, qt)       # standard buttons, the text field's context menu
    else:
        log.warning("No Qt translation for %s; standard buttons stay in English", code)

    _add(app, plater)
    QLocale.setDefault(locale)      # dates and the calendar popup
    log.info("Interface language %s", code)
    return True


def uninstall() -> None:
    for translator in _installed:
        QCoreApplication.removeTranslator(translator)
    _installed.clear()
    QLocale.setDefault(QLocale.system())


def message_text(template: str, values: Mapping[str, object] | None = None) -> str:
    """A template marked with QT_TRANSLATE_NOOP, translated and filled in."""

    return fill(QCoreApplication.translate(CONTEXT, template), values)


def error_text(error: AppError) -> str:
    """What to tell the user about `error`."""

    if error.user_message:
        return message_text(error.user_message, error.context)
    return str(error)


def diagnostic_text(item: Diagnostic) -> str:
    return message_text(item.message, item.context)


def severity_label(severity: Severity) -> str:
    if severity is Severity.ERROR:
        return QCoreApplication.translate("i18n", "Error")
    return QCoreApplication.translate("i18n", "Warning")


def _install_english(app: QCoreApplication, directory: Path) -> None:
    """English is the source text and needs no translation. Only its plural 
    forms ("1 template" vs "1 template(s)") need one. plater_en.qm holds nothing else. 
    Without it the source text is shown.
    """

    english = QTranslator(app)
    if english.load("plater_en", str(directory)):
        _add(app, english)


def _add(app: QCoreApplication, translator: QTranslator) -> None:
    app.installTranslator(translator)
    _installed.append(translator)