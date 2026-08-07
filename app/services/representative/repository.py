from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.organization import Organization
from app.db.models.core.representative import Representative
from app.db.models.core.representative_localization import RepresentativeLocalization
from app.db.models.references.language import Language
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.sentinel import UNSET, Unset


@dataclass(slots=True, frozen=True)
class RepresentativeText:
    """One language's worth of a representative's identity."""

    name: str
    title: str | None = None


class RepresentativeRepository:
    """Representatives are shared between organizations, so they are their own aggregate."""

    def __init__(self, session: Session) -> None:
        self._session = session


    def create(
            self,
            localizations: Mapping[str, RepresentativeText],
    ) -> Representative:

        self._check_localizations(localizations)

        representative = Representative(
            localizations={
                code: RepresentativeLocalization(
                    language_code=code,
                    name=text.name,
                    title=text.title,
                )
                for code, text in localizations.items()
            }
        )

        self._session.add(representative)
        self._session.commit()

        return representative


    def get(self, representative_id: int) -> Representative:
        representative = self._session.scalar(
            select(Representative)
            .where(Representative.id == representative_id)
            .options(
                selectinload(Representative.localizations),
                selectinload(Representative.organizations),
            )
        )

        if representative is None:
            raise EntityNotFound(
                f"representative {representative_id} not found",
                context={"representative_id": representative_id},
            )

        return representative


    def list(
            self,
            *,
            search: str | None = None,
            organization_id: int | None = None,
    ) -> list[Representative]:
        """Newest first; 'search' matches any localized name,
        and the filter narrows to one organization's people for a picker."""

        query = (
            select(Representative)
            .options(selectinload(Representative.localizations))
            .order_by(Representative.id.desc())
        )

        if search:
            query = query.where(
                Representative.id.in_(
                    select(RepresentativeLocalization.representative_id)
                    .where(RepresentativeLocalization.name.icontains(search)),
                )
            )

        if organization_id is not None:
            query = query.where(
                Representative.organizations.any(Organization.id == organization_id),
            )

        return list(self._session.scalars(query).unique().all())


    def update(
            self,
            representative_id: int,
            *,
            localizations: Mapping[str, RepresentativeText] | Unset = UNSET,
    ) -> Representative:

        representative = self.get(representative_id)
        if isinstance(localizations, Unset):
            return representative

        self._check_localizations(localizations)

        current = representative.localizations

        for code, text in localizations.items():
            row = current.get(code)

            if row is None:
                current[code] = RepresentativeLocalization(
                    language_code=code,
                    name=text.name,
                    title=text.title,
                )
            else:
                row.name = text.name
                row.title = text.title

        for code in set(current) - set(localizations):
            del current[code]

        self._session.commit()

        return representative


    def delete(self, representative_id: int) -> None:
        """Refused while still attached to any organization."""

        representative = self.get(representative_id)

        if representative.organizations:
            raise InvalidSelection(
                f"representative {representative_id} is still attached to "
                f"{len(representative.organizations)} organization(s)",
                user_message="Detach selected representative from every organization first.",
                context={
                    "representative_id": representative_id,
                    "organization_ids": [ o.id for o in representative.organizations ],
                }
            )

        self._session.delete(representative)
        self._session.commit()


    def _check_localizations(
            self,
            localizations: Mapping[str, RepresentativeText],
    ) -> None:

        if not localizations:
            raise InvalidSelection(
                "representative needs at least one localization",
                user_message="Enter the representative's name in at least one language.",
            )

        for code in localizations:
            if self._session.get(Language, code) is None:
                raise EntityNotFound(
                    f"language {code!r} not found",
                    context={"code": code},
                )