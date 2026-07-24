from app.core.diagnostics import DiagnosticCollector

from app.document_engine.normalization.models.blocks import NormalizedBlock
from app.document_engine.normalization.models.sections import NormalizedSection
from app.document_engine.normalization.normalizers.paragraphs import normalize_paragraph
from app.document_engine.normalization.normalizers.tables import normalize_table
from app.document_engine.normalization.normalizers.sections import normalize_section
from app.document_engine.normalization.errors import NormalizationFormatError

from app.document_engine.parser.models.blocks import ParagraphNode, TableNode, SectionBreakNode



class StructuralNormalizer:

    @classmethod
    def normalize(
            cls,
            parsed_blocks: list[ParagraphNode | TableNode | SectionBreakNode],
            diagnostics: DiagnosticCollector,
        ) -> list[NormalizedSection]:

        if not parsed_blocks:
            raise NormalizationFormatError(
                "Parser returned empty list."
            )

        sections = []
        current_section_blocks: list[NormalizedBlock] = []

        for item in parsed_blocks:
            if isinstance(item, ParagraphNode):
                current_section_blocks.append(normalize_paragraph(item))

            elif isinstance(item, TableNode):
                current_section_blocks.append(normalize_table(item, diagnostics))

            elif isinstance(item, SectionBreakNode):
                sections.append(
                    normalize_section(
                        ancestor=item,
                        blocks=current_section_blocks,
                    )
                )
                current_section_blocks = []
            
            else:
                raise NormalizationFormatError(
                    "Invalid parsed object type."
                )

        if current_section_blocks:
            raise NormalizationFormatError(
                "Document ended without a SectionBreakNode."
            )

        return sections