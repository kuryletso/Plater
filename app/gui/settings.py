from __future__ import annotations

from PySide6.QtCore import QSettings

from app.paths import settings_path

UI_LANGUAGE = "ui/language"
DEFAULT_LANGUAGE = "ENG"
SUPPORTED_LANGUAGES = ("ENG", "UKR")

def ui_language() -> str:
    """Validates UI language value since settings file can be hand-edited."""

    value = _store().value(UI_LANGUAGE, DEFAULT_LANGUAGE)
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_ui_language(code: str) -> None:
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported UI language {code!r}")

    settings_path().parent.mkdir(parents=True, exist_ok=True)

    store = _store()
    store.setValue(UI_LANGUAGE, code)
    store.sync()


def display_languages(code: str | None = None) -> tuple[str, ...]:
    """Orders selected language first, the other behind it."""

    selected = code or ui_language()
    return (selected, *( s for s in SUPPORTED_LANGUAGES if s != selected))


def _store() -> QSettings:
    """An .ini beside the database, readable and copyable preferences."""

    return QSettings(str(settings_path()), QSettings.Format.IniFormat)