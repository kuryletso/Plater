from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.assets.provider import DbAssetProvider
from app.core.diagnostics import DiagnosticCollector
from app.document_engine.orchestration.pipeline import TemplateRenderingPipeline
from app.services.doc_sequence.repository import IssuedNumber, SequenceRepository
from app.services.errors import InvalidSelection, SequenceConflict
from app.services.invoice.assembler import (
    InvoiceAssembler, build_labels, resolve_languages,
)
from app.services.invoice.draft import InvoiceDraft
from app.services.invoice.mapper import InvoiceMapper
from app.services.template.repository import TemplateRepository


@dataclass(slots=True, frozen=True)
class GenerationResult:
    """'number' is what the document carries. Trust it only when 'succeeded'."""

    docx: bytes | None
    number: IssuedNumber
    diagnostics: DiagnosticCollector

    @property
    def succeeded(self) -> bool:
        return self.docx is not None


class InvoiceGenerateService:
    """Assemble -> render -> consume-on-success.
    
    The single place SequenceRepository.consume() is called: a failed render
    must not burn a number, and nothing else may advance the counter.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._templates = TemplateRepository(session)
        self._sequences = SequenceRepository(session)


    def preview(self, draft: InvoiceDraft) -> GenerationResult:
        """Render without advancing the counter. Previews must not burn numbers."""

        return self._render(draft, self._sequences.peek(draft.sequence_id))


    def generate(self, draft: InvoiceDraft) -> GenerationResult:
        number = self._sequences.peek(draft.sequence_id)

        result = self._render(draft, number)
        if not result.succeeded:
            return result

        consumed = self._sequences.consume(draft.sequence_id)
        if consumed != number:
            raise SequenceConflict(
                f"rendered {number.formatted!r} but consumed {consumed.formatted!r}",
                user_message="The document number changed during generation. "
                             "Generate the document again.",
                context={"rendered": number.formatted, "consumed": consumed.formatted},
            )

        return result


    def _render(
            self,
            draft: InvoiceDraft,
            number: IssuedNumber,
    ) -> GenerationResult:

        template = self._templates.get(draft.template_id)
        self._check_document_type(draft, template.type)
        
        blueprint = self._templates.get_blueprint(draft.template_id)

        languages = resolve_languages(self._session, blueprint.config)
        codes = tuple( lang.code for lang in languages )

        data = InvoiceAssembler(self._session, languages).assemble(draft, number)
        context = InvoiceMapper(
            languages,
            build_labels(self._session, codes),
            blueprint.config.append_currency,
        ).map(data)

        render = TemplateRenderingPipeline(DbAssetProvider(self._session)).render(blueprint, context)

        return GenerationResult(
            docx=render.docx,
            number=number,
            diagnostics=render.diagnostics,
        )


    def _check_document_type(
            self,
            draft: InvoiceDraft,
            template_type: str,
    ) -> None:

        sequence = self._sequences.get(draft.sequence_id)

        if sequence.document_type_code != template_type:
            raise InvalidSelection(
                f"sequence {draft.sequence_id} numbers "
                f"{sequence.document_type_code!r} documents, template "
                f"{draft.template_id} is {template_type!r}",
                user_message="The numbering sequence does not match the "
                             "document type of the selected template.",
                context={
                    "sequence_id": draft.sequence_id,
                    "sequence_type": sequence.document_type_code,
                    "template_id": draft.template_id,
                    "template_type": template_type,
                },
            )