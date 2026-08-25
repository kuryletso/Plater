from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.references.language import Language
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.db.models.registries.measurement_unit_localization import MeasurementUnitRegistryLocalization
from app.services.errors import EntityNotFound, InvalidSelection


@dataclass(slots=True, frozen=True)
class MeasurementUnitText:
    name: str


def normalize_code(code: str) -> str:
    return "_".join(code.strip().lower().split())


class MeasurementUnitRepository:
    def __init__(self, session: Session) -> None:
        self._session = session


    def create(
            self,
            code: str,
            localizations: Mapping[str, MeasurementUnitText],
    ) -> MeasurementUnitRegistry:

        code = normalize_code(code)
        if not code:
            raise InvalidSelection(
                "measurement unit code cannot be empty",
                user_message="Enter a short code for the unit.",
            )

        self._check_localizations(localizations)

        if self._session.get(MeasurementUnitRegistry, code) is not None:
            raise InvalidSelection(
                f"measurement unit {code!r} already exists",
                user_message=f"A unit with the code '{code}' already exists.",
                context={"code": code},
            )

        unit = MeasurementUnitRegistry(
            code=code,
            system=False,
            active=True,
            localizations={
                language: MeasurementUnitRegistryLocalization(
                    language_code=language,
                    name=text.name,
                )
                for language, text in localizations.items()
            },
        )

        self._session.add(unit)
        self._session.commit()

        return unit


    def list(
            self,
            *,
            search: str | None = None,
            include_inactive: bool = False,
    ) -> list[MeasurementUnitRegistry]:
        """Code order. 'Search' matches the code or any localized name."""

        query = (
            select(MeasurementUnitRegistry)
            .options(selectinload(MeasurementUnitRegistry.localizations))
            .order_by(MeasurementUnitRegistry.code)
        )
        if not include_inactive:
            query = query.where(MeasurementUnitRegistry.active.is_(True))

        rows = list(self._session.scalars(query).unique().all())
        if not search:
            return rows

        needle = search.casefold()
        return [
            unit for unit in rows
            if needle in unit.code.casefold()
            or any( needle in row.name.casefold() for row in unit.localizations.values() )
        ]


    def _check_localizations(
            self,
            localizations: Mapping[str, MeasurementUnitText],
    ) -> None:

        if not localizations:
            raise InvalidSelection(
                "measurement unit needs at least oen localization",
                user_message="Enter the unit name in at least one language.",
            )

        for code in localizations:
            if self._session.get(Language, code) is None:
                raise EntityNotFound(
                    f"language {code!r} not found",
                    context={"code": code},
                )