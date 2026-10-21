"""Resolves issue date in documents. Template holds pattern.

Patterns are Unicode (CLDR) date patterns, formatted and translated by Babel.
"""

from __future__ import annotations

from datetime import date

from babel import UnknownLocaleError
from babel.dates import format_date

from app.core.messages import QT_TRANSLATE_NOOP
from app.services.errors import InvalidSelection

ISO = "y-MM-dd"
DATE_FORMATS = (ISO, "dd.MM.y", "MM/dd/y", "d MMMM y", "MMMM d, y")
DEFAULT_DATE_FORMAT = ISO


def format_document_date(value: date, pattern: str, language: str | None) -> str:
    """`language` is ISO 639-1 ('uk'). Language not know by Babel falls back to English."""

    try:
        return format_date(value, pattern, locale=language or "en")
    except (UnknownLocaleError, ValueError, TypeError):
        return format_date(value, pattern, locale="en")


def check_date_format(pattern: str) -> str:
    if pattern not in DATE_FORMATS:
        raise InvalidSelection(
            f"unknown date format {pattern!r}",
            user_message=QT_TRANSLATE_NOOP("messages", "Select a date format."),
            context={"pattern": pattern},
        )
    return pattern