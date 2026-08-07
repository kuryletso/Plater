from __future__ import annotations

from typing import Final


class Unset:
    """Sentinel type: 'str | None | Unset' narrows correctly under isinstance."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = Unset()