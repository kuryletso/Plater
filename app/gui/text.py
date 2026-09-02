from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_preferred: tuple[str, ...] = ("ENG", "UKR")


def set_preferred_languages(codes: tuple[str, ...]) -> None:
    """Sets preferred languages global since localized() is called from everywhere."""

    global _preferred
    _preferred = codes or ("ENG",)


def preferred_languages() -> tuple[str, ...]:
    return _preferred


def localized(localizations: Mapping[str, Any], attr: str) -> str:
    for code in _preferred:
        row = localizations.get(code)
        if row is not None and getattr(row, attr):
            return getattr(row, attr)

    for row in localizations.values():
        if getattr(row, attr):
            return getattr(row, attr)

    return "?"


def ordered_localizations(localizations: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Preferred languages first, then anything else the entity happens to have."""

    codes  = [ code for code in _preferred if code in localizations ]
    codes += [ code for code in localizations if code not in codes ]
    return [ (code, localizations[code]) for code in codes ]


def organization_label(organization: Any) -> str:
    """Two lines: legal form + name per language, then the first tax identifier."""

    names = [
        " ".join( part for part in (row.org_type, row.legal_name) if part )
        for _, row in ordered_localizations(organization.localizations)
    ]
    label = " / ".join( name for name in names if name ) or "?"

    tax = next(iter(organization.tax_ids), None)
    if tax is not None:
        system = localized(tax.tax_id_system.localizations, "name")
        label += f"\n{system} {tax.value}"

    return label