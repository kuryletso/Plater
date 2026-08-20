from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PREFERRED_LANGUAGES = ("ENG", "UKR")


def localized(localizations: Mapping[str, Any], attr: str) -> str:
    for code in PREFERRED_LANGUAGES:
        row = localizations.get(code)
        if row is not None and getattr(row, attr):
            return getattr(row, attr)

    for row in localizations.values():
        if getattr(row, attr):
            return getattr(row, attr)

    return "?"