"""Regressions found by ingesting real Google Docs / Word templates.

Every ``xfail(strict=True)`` here is an open task from the 2026-09-04 manual test
pass. Fixing the task turns the test into an XPASS *failure*, which is the signal
to drop the marker — so this module doubles as the checklist.

See tests/fixtures/real_templates/README.md for what each file exercises.
"""

import io
import zipfile

from lxml import etree
import pytest

from app.core.diagnostics import DiagnosticCollector
from app.document_engine.blueprint.models.paragraph import ParagraphBlueprint
from app.document_engine.blueprint.models.segment import (
    GroupedPlaceholderSegment,
    JoinedPlaceholderSegment,
    PlaceholderSegment,
    TextSegment,
)
from app.document_engine.blueprint.models.table import (
    CellBlueprint,
    CellPlaceholder,
    TableBlueprint,
    TablePlaceholder,
)
from app.document_engine.enums.enums import PlaceholderType
from app.document_engine.orchestration.pipeline import TemplateRenderingPipeline
from app.document_engine.parser.parser import DocxParser
from app.document_engine.normalization.normalizers.paragraphs import normalize_paragraph
from app.document_engine.rendering.context import (
    InvoiceLineRow,
    InvoiceTableData,
    RenderContext,
)
from app.document_engine.rendering.docx.emitter import DocxEmitter
from app.document_engine.rendering.resolve.resolver import DocumentResolver


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

TASK = "open task from the 2026-09-04 manual test pass"


class NoAssets:
    def get(self, asset_id):
        return None


# --- blueprint walkers -------------------------------------------------------

def _blocks(blueprint):
    """Every block in the document, tables and cells flattened in."""

    def walk(blocks):
        for block in blocks:
            yield block
            if isinstance(block, TableBlueprint):
                for row in block.rows:
                    for cell in row.cells:
                        if isinstance(cell, CellBlueprint):
                            yield from walk(cell.blocks)

    for section in blueprint.sections:
        yield from walk(section.blocks)
        for group in (section.headers, section.footers):
            for hf in (group.default, group.first, group.even):
                if hf is not None:
                    yield from walk(hf.blocks)


def segments(blueprint):
    """Top-level segments of every paragraph, in document order."""
    for block in _blocks(blueprint):
        if isinstance(block, ParagraphBlueprint):
            yield from block.segments


def placeholders(blueprint):
    """Every PlaceholderSegment, including those nested in joined/grouped forms."""
    for segment in segments(blueprint):
        if isinstance(segment, PlaceholderSegment):
            yield segment
        elif isinstance(segment, JoinedPlaceholderSegment):
            yield from (i for i in segment.items if isinstance(i, PlaceholderSegment))
        elif isinstance(segment, GroupedPlaceholderSegment):
            for group in segment.items:
                yield from (i for i in group if isinstance(i, PlaceholderSegment))


def cell_placeholders(blueprint):
    for block in _blocks(blueprint):
        if isinstance(block, TableBlueprint):
            for row in block.rows:
                yield from (c for c in row.cells if isinstance(c, CellPlaceholder))


def texts(blueprint) -> list[str]:
    return [s.text for s in segments(blueprint) if isinstance(s, TextSegment)]


def codes(diagnostics) -> list[str]:
    return [item.code for item in diagnostics.items]


# --- render helpers ----------------------------------------------------------

def _document_xml(docx: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def render_raw_xml(blueprint) -> etree._Element:
    """Raw-render (KEYS mode) and hand back word/document.xml."""
    result = TemplateRenderingPipeline(NoAssets()).render_raw(blueprint)
    assert result.docx is not None
    return _document_xml(result.docx)


def render_values_xml(blueprint, context: RenderContext) -> etree._Element:
    """Resolve + emit directly, skipping validate_context.

    The pipeline's gate refuses a context with anything missing, which would make
    these assertions depend on unrelated open tasks. Everything downstream of the
    gate is the same code path.
    """

    resolved = DocumentResolver(context, NoAssets(), DiagnosticCollector()).resolve(blueprint)
    return _document_xml(DocxEmitter(DiagnosticCollector()).emit(resolved))


def every_value_context(
    blueprint,
    *,
    language: str = "ENG",
    columns_as_scalars: bool = False,
) -> RenderContext:
    """A context shaped the way InvoiceMapper shapes one: scalars and one table.

    ``columns_as_scalars`` is a crutch for the render tests. A standalone
    ``{{ invl_desc }}`` currently reaches ``DocumentResolver._value`` and raises,
    so filling it keeps those assertions independent of Task 6. Drop the argument
    once Task 6 lands.
    """

    keys = {
        p.key for p in placeholders(blueprint)
        if columns_as_scalars or p.ph_type is PlaceholderType.SCALAR
    }

    columns = (
        "invl_n", "invl_desc", "invl_unit",
        "invl_qnty", "invl_price", "invl_tax", "invl_total",
    )
    row = InvoiceLineRow(values={key: {language: f"<{key}>"} for key in columns})

    return RenderContext(
        scalars={key: {language: f"<{key}>"} for key in keys},
        table=InvoiceTableData(
            rows=(row, row),
            show_tax=True,
            subtotal={language: "100.00"},
            total_tax={language: "20.00"},
            total={language: "120.00"},
            labels={key: {language: key} for key in (*columns, "subtotal", "total_tax", "total")},
        ),
    )


def grids(document) -> list[list[int]]:
    return [
        [int(float(col.get(f"{W}w", "0"))) for col in grid.findall(f"{W}gridCol")]
        for grid in document.iter(f"{W}tblGrid")
    ]


# --- baseline: what already works -------------------------------------------

def test_empty_template_ingests_without_diagnostics(ingest_real):
    blueprint, diagnostics = ingest_real("empty")

    assert not diagnostics.has_errors
    assert list(placeholders(blueprint)) == []


def test_language_suffixes_resolve_to_concrete_codes(ingest_real):
    blueprint, _ = ingest_real("languages", primary="ENG", secondary="UKR")
    dates = [p for p in placeholders(blueprint) if p.key == "date"]

    # bare {{ date }} bakes in the primary language at ingestion
    assert {p.language for p in dates} == {"ENG", "UKR"}
    assert sum(p.language == "ENG" for p in dates) == 2


def test_unknown_keys_and_languages_degrade_to_literal_text(ingest_real):
    blueprint, diagnostics = ingest_real("languages_invalid", primary="ENG", secondary="UKR")

    assert not diagnostics.has_errors, "a bad placeholder must warn, never block import"
    assert "{{ foobar }}" in texts(blueprint)
    assert "{{ date.SPA }}" in texts(blueprint)
    assert {p.key for p in placeholders(blueprint)} <= {
        "date", "prefix", "client_name", "client_country", "client_address", "client_phone",
    }


def test_placeholder_split_by_a_line_break_still_resolves(ingest_real):
    """Shift+Enter inside {{ }} works today. Paragraph breaks do not (see below)."""
    blueprint, _ = ingest_real("languages_invalid", primary="ENG", secondary="UKR")

    assert any(p.key == "prefix" for p in placeholders(blueprint))


def test_invoice_table_becomes_a_table_placeholder_at_every_nesting_depth(ingest_real):
    """Five, not six: {{ invoice_table }} in one cell of a 3x3 table replaces the
    whole wrapper table, which is what _promote_placeholder_rows is for.
    """

    blueprint, _ = ingest_real("tables")
    tables = [b for b in _blocks(blueprint) if isinstance(b, TablePlaceholder)]

    assert len(tables) == 5
    assert all(t.language == "ENG" for t in tables)


def test_invoice_line_cells_become_cell_placeholders(ingest_real):
    blueprint, _ = ingest_real("tables")

    assert {c.key for c in cell_placeholders(blueprint)} == {
        "invl_n", "invl_desc", "invl_unit", "invl_price",
    }


# --- Task 4: escapes in a placeholder separator ------------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 4 — {TASK}: tokenizer drops the backslash")
def test_escaped_newline_in_a_separator_is_a_newline(ingest_real):
    r"""`sep="\n"` must join with a line break, not the letter n."""
    blueprint, _ = ingest_real("formatting")
    grouped = [s for s in segments(blueprint) if isinstance(s, GroupedPlaceholderSegment)]

    assert grouped, "the formatting template has grouped placeholders"
    assert all(g.separator == "\n" for g in grouped)


@pytest.mark.xfail(strict=True, reason=f"Task 4 — {TASK}")
def test_tokenizer_maps_the_standard_escapes():
    from app.document_engine.blueprint.builders.tokenizer import TK, tokenize_placeholder

    tokens = tokenize_placeholder(r'a, b, sep="\n\t\\\"x"')
    strings = [t.value for t in tokens if t.kind == TK.STRING]

    assert strings == ['\n\t\\"x']


# --- Task 5: the split-brace / multi-colour placeholder ----------------------

@pytest.mark.xfail(strict=True, reason=f"Task 5 — {TASK}: '{{' split across runs is not seen")
def test_placeholder_split_across_two_runs_at_the_braces(make_runs):
    """A colour change between `{` and `{` must not hide the placeholder.

    Real editors split runs per character when text is painted letter by letter,
    so the opening brace itself lands in a run of its own.
    """

    path = make_runs([("{", False), ("{ org_name }}", True)])
    with DocxParser(path, diagnostics=DiagnosticCollector()) as parser:
        parsed = parser.parse()

    paragraph = normalize_paragraph(parsed.sections[0].blocks[0])

    assert len(paragraph.inlines) == 1
    assert paragraph.inlines[0].text == "{{ org_name }}"


@pytest.mark.xfail(strict=True, reason=f"Task 5 — {TASK}")
def test_a_multicoloured_placeholder_resolves(ingest_real):
    """formatting.docx paints one {{ client_name }} a letter per colour."""
    blueprint, _ = ingest_real("formatting")

    assert "{" not in "".join(texts(blueprint))
    assert sum(p.key == "client_name" for p in placeholders(blueprint)) == 8


# --- Task 6: invoice-line placeholders outside a table -----------------------

@pytest.mark.xfail(strict=True, reason=f"Task 6 — {TASK}: ingestion is silent")
def test_a_column_placeholder_outside_a_table_warns_at_ingestion(ingest_real):
    """{{ invl_desc }} in a plain paragraph cannot expand; say so on import."""
    _, diagnostics = ingest_real("tables")

    assert "column_placeholder_outside_table" in codes(diagnostics)
    assert not diagnostics.has_errors


@pytest.mark.xfail(strict=True, reason=f"Task 6 — {TASK}: reported as a missing scalar")
def test_a_column_placeholder_outside_a_table_does_not_block_rendering(ingest_real):
    """This is what stopped TEST-004 generating: validate_context files a COLUMN
    placeholder under `scalars`, finds nothing there, and errors.
    """

    from app.document_engine.rendering.validate import validate_context

    blueprint, _ = ingest_real("tables")
    diagnostics = DiagnosticCollector()
    validate_context(blueprint, every_value_context(blueprint), diagnostics)

    missing = [
        item for item in diagnostics.items
        if item.code == "missing_required_value"
        and (item.context or {}).get("key", "").startswith("invl_")
    ]
    assert missing == []


def test_column_placeholders_keep_their_type_through_ingestion(ingest_real):
    """Guard on the fix above: they must stay COLUMN, not be rewritten to SCALAR."""
    blueprint, _ = ingest_real("tables")
    standalone = [p for p in placeholders(blueprint) if p.key.startswith("invl_")]

    assert standalone
    assert all(p.ph_type is PlaceholderType.COLUMN for p in standalone)


# --- Task 7: titlePg must mirror the source ----------------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 7 — {TASK}: titlePg is invented")
def test_titlepg_is_not_invented(ingest_real):
    """layout.docx declares a `first` header but no <w:titlePg/>, so Word shows the
    default header on page 1. Emitting titlePg blanks the first page instead.
    """

    blueprint, _ = ingest_real("layout")
    document = render_raw_xml(blueprint)

    assert document.find(f".//{W}titlePg") is None


# --- Task 9: the system invoice table's column widths ------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 9 — {TASK}: 7 x 2400 twips overflows the page")
def test_a_standalone_invoice_table_fits_the_page(ingest_real):
    blueprint, _ = ingest_real("tables")
    document = render_values_xml(
        blueprint, every_value_context(blueprint, columns_as_scalars=True),
    )

    section = blueprint.sections[0].style
    usable = section.page_width - section.margins.left - section.margins.right

    for widths in grids(document):
        assert sum(widths) <= usable, (
            f"table grid is {sum(widths)} twips, page allows {usable}"
        )


@pytest.mark.xfail(strict=True, reason=f"Task 9 — {TASK}: every column gets the same width")
def test_the_invoice_table_does_not_use_equal_column_widths(ingest_real):
    """A '#' column as wide as 'Description' is what equal widths look like."""
    blueprint, _ = ingest_real("tables")
    document = render_values_xml(
        blueprint, every_value_context(blueprint, columns_as_scalars=True),
    )

    seven = [widths for widths in grids(document) if len(widths) == 7]

    assert seven, "the value render builds the full seven-column invoice table"
    assert any(len(set(widths)) > 1 for widths in seven)


# --- Task 10: page breaks ----------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 10 — {TASK}: w:br type=page is dropped at parse")
def test_a_page_break_survives_to_the_rendered_document(ingest_real):
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    breaks = [
        element for element in document.iter(f"{W}br")
        if element.get(f"{W}type") == "page"
    ]
    assert len(breaks) >= 3


# --- Task 11: line spacing ---------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 11 — {TASK}: w:line is never parsed or emitted")
def test_line_spacing_survives(ingest_real):
    """The source sets 2.0 line spacing on a run of paragraphs; we emit single."""
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    lines = {
        element.get(f"{W}line")
        for element in document.iter(f"{W}spacing")
        if element.get(f"{W}line")
    }
    assert lines != set()


# --- Task 12: table alignment ------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"Task 12 — {TASK}: tables have no alignment field")
def test_table_alignment_survives(ingest_real):
    """A right-aligned table came out left-aligned; <w:jc> is never emitted."""
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    aligned = [
        element for element in document.iter(f"{W}tblPr")
        if element.find(f"{W}jc") is not None
    ]
    assert aligned


# --- Task 22 (post-1.0): placeholders split by a paragraph break -------------

@pytest.mark.xfail(strict=True, reason="Task 22 — deferred post-1.0 ergonomics")
def test_a_placeholder_split_by_a_paragraph_break_resolves(ingest_real):
    """Writing a grouped placeholder across Enter presses.

    Shift+Enter already works (see above), so this is convenience, not correctness.
    """

    blueprint, diagnostics = ingest_real("languages_invalid", primary="ENG", secondary="UKR")

    assert "unclosed_placeholder" not in codes(diagnostics)
    assert "{{ date" not in "".join(texts(blueprint))
