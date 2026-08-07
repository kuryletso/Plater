from __future__ import annotations

from typing import cast

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db.models.core.document_sequence import DocumentSequence
from app.db.models.core.organization import Organization
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.services.sentinel import Unset, UNSET
from app.services.errors import EntityNotFound, InvalidSelection


@dataclass(slots=True, frozen=True)
class IssuedNumber:
    """Document number kept in two parts because templates place them separately."""

    prefix: str | None
    number: str

    @property
    def formatted(self) -> str:
        return f"{self.prefix or ''}{self.number}"


class SequenceRepository:

    def __init__(self, session: Session) -> None:
        self._session = session


    def create(
            self,
            organization_id: int,
            document_type: str,
            *,
            prefix: str | None = None,
            counter: int = 0,
            padding: int = 0,
    ) -> DocumentSequence:

        self._check_organization(organization_id)
        self._check_document_type(document_type)

        prefix = prefix or None
        self._check_counter(counter)
        self._check_padding(padding)

        clash = self._session.scalar(
            select(DocumentSequence)
            .where(
                DocumentSequence.organization_id == organization_id,
                DocumentSequence.document_type_code == document_type,
                DocumentSequence.prefix == prefix,
            )
        )
        if clash is not None:
            raise InvalidSelection(
                f"organization {organization_id} already numbers {document_type!r} "
                f"documents with prefix {prefix!r}",
                user_message="Numbering sequence with that prefix already exists.",
                context={
                            "organization_id": organization_id,
                            "document_type": document_type,
                            "prefix": prefix,
                        }
            )

        sequence = DocumentSequence(
            organization_id=organization_id,
            document_type_code=document_type,
            prefix=prefix,
            counter=counter,
            padding=padding,
        )

        self._session.add(sequence)
        self._session.commit()

        return sequence


    def get(self, sequence_id: int) -> DocumentSequence:
        sequence = self._session.scalar(
            select(DocumentSequence)
            .where(DocumentSequence.id == sequence_id)
            .options(
                selectinload(DocumentSequence.organization),
            ),
        )

        if sequence is None:
            raise EntityNotFound(
                f"document sequence {sequence_id} not found",
                context={"sequence_id": sequence_id},
            )

        return sequence


    def list(
            self,
            *,
            organization_id: int | None = None,
            document_type: str | None = None,
    ) -> list[DocumentSequence]:

        query = select(DocumentSequence).order_by(DocumentSequence.id)

        if organization_id is not None:
            query = query.where(DocumentSequence.organization_id == organization_id)
        if document_type is not None:
            query = query.where(DocumentSequence.document_type_code == document_type)

        return list(self._session.scalars(query).all())


    def update(
            self,
            sequence_id: int,
            *,
            prefix: str | None | Unset = UNSET,
            counter: int | Unset = UNSET,
            padding: int | Unset = UNSET,
    ) -> DocumentSequence:

        sequence = self.get(sequence_id)

        new_prefix = sequence.prefix if isinstance(prefix, Unset) else (prefix or None)

        if not isinstance(counter, Unset):
            self._check_counter(counter)
        if not isinstance(padding, Unset):
            self._check_padding(padding)

        if new_prefix != sequence.prefix:
            clash = self._session.scalar(
                select(DocumentSequence)
                .where(
                    DocumentSequence.organization_id == sequence.organization_id,
                    DocumentSequence.document_type_code == sequence.document_type_code,
                    DocumentSequence.prefix == new_prefix,
                    DocumentSequence.id != sequence_id,
                )
            )

            if clash is not None:
                raise InvalidSelection(
                    f"prefix {new_prefix!r} is already used for this document type",
                    user_message="Numbering sequence with that prefix already exists.",
                    context={"prefix": new_prefix},
                )

        sequence.prefix = new_prefix

        if not isinstance(counter, Unset):
            sequence.counter = counter
        if not isinstance(padding, Unset):
            sequence.padding = padding

        self._session.commit()

        return sequence


    def delete(self, sequence_id: int) -> None:
        """Refused once number have been issued."""

        sequence = self.get(sequence_id)

        self._session.delete(sequence)
        self._session.commit()


    def peek(self, sequence_id: int) -> IssuedNumber:
        """The number a document *would* get. Previewing must not burn one."""

        sequence = self.get(sequence_id)

        return self._format(sequence, sequence.counter + 1)


    def consume(self, sequence_id: int) -> IssuedNumber:
        """Reserve the next number. One statement, so concurrent renders cannot collide."""

        sequence = self.get(sequence_id)

        issued = self._session.scalar(
            update(DocumentSequence)
            .where(DocumentSequence.id == sequence_id)
            .values(counter=DocumentSequence.counter + 1)
            .returning(DocumentSequence.counter)
        )

        self._session.commit()
        self._session.refresh(sequence)

        return self._format(sequence, cast(int, issued))


    def _format(
            self,
            sequence: DocumentSequence,
            counter: int,
    ) -> IssuedNumber:

        return IssuedNumber(
            prefix=sequence.prefix,
            number=str(counter).zfill(sequence.padding),
        )


    def _check_organization(self, organization_id: int) -> None:
        if self._session.get(Organization, organization_id) is None:
            raise EntityNotFound(
                f"organization {organization_id} not found",
                context={"organization_id": organization_id},
            )


    def _check_document_type(self, code: str) -> None:
        row = self._session.get(DocumentTypeRegistry, code)

        if row is None:
            raise EntityNotFound(
                f"document type {code!r} not found",
                context={"code": code},
            )

        if not row.active:
            raise InvalidSelection(
                f"document type {code!r} is disabled",
                user_message="Selected document type is no longer available.",
                context={"code": code},
            )


    def _check_counter(self, counter: int) -> None:
        if counter < 0:
            raise InvalidSelection(
                f"counter cannot be negative, got {counter}",
                user_message="The counter cannot be negative.",
                context={"counter": counter},
            )


    def _check_padding(self, padding: int) -> None:
        if padding < 0:
            raise InvalidSelection(
                f"padding cannot be negative, got {padding}",
                user_message="The padding cannot be negative.",
                context={"padding": padding},
            )