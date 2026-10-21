from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QByteArray

from app.paths import settings_path

UI_LANGUAGE = "ui/language"
DEFAULT_LANGUAGE = "ENG"
SUPPORTED_LANGUAGES = ("ENG", "UKR")
LAST_SAVE_DIR = "files/last_save_dir"
WINDOW_GEOMETRY = "window/geometry"


def ui_language() -> str:
    """Validates UI language value since settings file can be hand-edited."""

    value = _store().value(UI_LANGUAGE, DEFAULT_LANGUAGE)
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_ui_language(code: str) -> None:
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported UI language {code!r}")

    _write(UI_LANGUAGE, code)

    # settings_path().parent.mkdir(parents=True, exist_ok=True)

    # store = _store()
    # store.setValue(UI_LANGUAGE, code)
    # store.sync()


def display_languages(code: str | None = None) -> tuple[str, ...]:
    """Orders selected language first, the other behind it."""

    selected = code or ui_language()
    return (selected, *( s for s in SUPPORTED_LANGUAGES if s != selected))


def last_save_dir() -> Path | None:
    """None means unset or since deleted, the save dialog then falls back to default Documents."""

    value = _store().value(LAST_SAVE_DIR)
    path = Path(value) if isinstance(value, str) and value else None
    return path if path is not None and path.is_dir() else None


def set_last_save_dir(folder: Path) -> None:
    _write(LAST_SAVE_DIR, str(folder))


def window_geometry() -> QByteArray | None:
    value = _store().value(WINDOW_GEOMETRY)
    return value if isinstance(value, QByteArray) and not value.isEmpty() else None


def set_window_geometry(geometry: QByteArray) -> None:
    _write(WINDOW_GEOMETRY, geometry)


def _write(key: str, value: object) -> None:
    settings_path().parent.mkdir(parents=True, exist_ok=True)

    store = _store()
    store.setValue(key, value)
    store.sync()


def _store() -> QSettings:
    """An .ini beside the database, readable and copyable preferences."""

    return QSettings(str(settings_path()), QSettings.Format.IniFormat)