"""Regressions found by ingesting real Google Docs / Word templates.

Every ``xfail(strict=True)`` here is an open task from the 2026-09-04 manual test
pass. Fixing the task turns the test into an XPASS *failure*, which is the signal
to drop the marker — so this module doubles as the checklist.

See tests/fixtures/real_templates/README.md for what each file exercises.
"""

import io
from collections import Counter
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
from app.document_engine.parser.models.blocks import ParagraphNode
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


def every_value_context(blueprint, *, language: str = "ENG") -> RenderContext:
    """A context shaped the way InvoiceMapper shapes one: scalars and one table.

    COLUMN placeholders stay out of the scalars, as they do in the mapper; one
    outside a table row must render empty rather than raise (Task 6).
    """

    keys = {
        p.key for p in placeholders(blueprint)
        if p.ph_type is PlaceholderType.SCALAR
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

def test_escaped_newline_in_a_separator_is_a_newline(ingest_real):
    r"""`sep="\n"` must join with a line break, not the letter n.

    The same template also uses `sep=" | "` and `sep=" ::: "`, which must come
    through untouched — the escape map has to be a lookup, not a rewrite.
    """

    blueprint, _ = ingest_real("formatting")
    separators = {
        segment.separator for segment in segments(blueprint)
        if isinstance(segment, (GroupedPlaceholderSegment, JoinedPlaceholderSegment))
    }

    assert "\n" in separators
    assert "n" not in separators
    assert {" | ", " ::: "} <= separators


def test_an_escaped_newline_separator_emits_a_line_break(ingest_real):
    """End of the chain: the run builder splits on \\n and writes <w:br/>."""

    blueprint, _ = ingest_real("formatting")
    document = render_values_xml(
        blueprint, every_value_context(blueprint),
    )

    soft_breaks = [
        element for element in document.iter(f"{W}br")
        if element.get(f"{W}type") is None
    ]
    assert soft_breaks


def test_tokenizer_maps_the_standard_escapes():
    from app.document_engine.blueprint.builders.tokenizer import TK, tokenize_placeholder

    tokens = tokenize_placeholder(r'a, b, sep="\n\t\\\"x"')
    strings = [t.value for t in tokens if t.kind == TK.STRING]

    assert strings == ['\n\t\\"x']


# --- Task 5: the split-brace / multi-color placeholder ----------------------

def test_placeholder_split_across_two_runs_at_the_braces(make_runs):
    """A color change between `{` and `{` must not hide the placeholder.

    Real editors split runs per character when text is painted letter by letter,
    so the opening brace itself lands in a run of its own.
    """

    path = make_runs([("{", False), ("{ org_name }}", True)])
    with DocxParser(path, diagnostics=DiagnosticCollector()) as parser:
        parsed = parser.parse()

    paragraph = normalize_paragraph(
        next(block for block in parsed if isinstance(block, ParagraphNode))
    )

    assert len(paragraph.inlines) == 1
    assert paragraph.inlines[0].text == "{{ org_name }}"


def test_a_multicolored_placeholder_resolves(ingest_real):
    """formatting.docx paints one {{ client_name }} a letter per color."""
    blueprint, _ = ingest_real("formatting")

    assert "{" not in "".join(texts(blueprint))
    # 4 alignment groups + 1 table group + 3 merged cells + 4 font lines
    # + 4 formatting lines; one of the font lines is the rainbow one
    assert sum(p.key == "client_name" for p in placeholders(blueprint)) == 16


# --- Task 6: invoice-line placeholders outside a table -----------------------

def test_a_column_placeholder_outside_a_table_warns_at_ingestion(ingest_real):
    """{{ invl_desc }} in a plain paragraph cannot expand; say so on import."""
    _, diagnostics = ingest_real("tables")

    assert "column_placeholder_outside_table" in codes(diagnostics)
    assert not diagnostics.has_errors


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

def test_titlepg_is_not_invented(ingest_real):
    """layout.docx declares a `first` header but no <w:titlePg/>, so Word shows the
    default header on page 1. Emitting titlePg blanks the first page instead.
    """

    blueprint, _ = ingest_real("layout")
    document = render_raw_xml(blueprint)

    assert document.find(f".//{W}titlePg") is None


def test_titlepg_survives_when_the_source_declares_it(tmp_path, fixture_provider):
    """The other direction: a genuine "different first page" must be kept."""
    from docx import Document
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    document = Document()
    document.add_paragraph("Invoice for {{ org_name }}")
    section = document.sections[0]
    section.different_first_page_header_footer = True
    section.first_page_header.paragraphs[0].text = "First page only"
    path = tmp_path / "title_page.docx"
    document.save(path)

    pipeline = TemplateIngestionPipeline(fixture_provider)
    blueprint = pipeline.finalize(pipeline.ingest(path).draft)

    assert blueprint.sections[-1].style.title_page is True
    assert render_raw_xml(blueprint).find(f".//{W}titlePg") is not None


# --- Task 9: the system invoice table's column widths ------------------------

def test_a_standalone_invoice_table_fits_the_page(ingest_real):
    blueprint, _ = ingest_real("tables")
    document = render_values_xml(
        blueprint, every_value_context(blueprint),
    )

    section = blueprint.sections[0].style
    usable = section.page_width - section.margins.left - section.margins.right

    for widths in grids(document):
        assert sum(widths) <= usable, (
            f"table grid is {sum(widths)} twips, page allows {usable}"
        )


def test_the_invoice_table_does_not_use_equal_column_widths(ingest_real):
    """A '#' column as wide as 'Description' is what equal widths look like."""
    blueprint, _ = ingest_real("tables")
    document = render_values_xml(
        blueprint, every_value_context(blueprint),
    )

    seven = [widths for widths in grids(document) if len(widths) == 7]

    assert seven, "the value render builds the full seven-column invoice table"
    assert any(len(set(widths)) > 1 for widths in seven)


# --- Task 10: page breaks ----------------------------------------------------

def test_a_page_break_survives_to_the_rendered_document(ingest_real):
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    breaks = [
        element for element in document.iter(f"{W}br")
        if element.get(f"{W}type") == "page"
    ]
    assert len(breaks) == 4         # formatting.docx has exactly four


# --- Task 11: line spacing ---------------------------------------------------

def test_line_spacing_survives(ingest_real):
    """The source sets 2.0 line spacing on a run of paragraphs; we emit single."""
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    lines = {
        element.get(f"{W}line")
        for element in document.iter(f"{W}spacing")
        if element.get(f"{W}line")
    }
    # 1.15 inherited from docDefaults (what the report was about), and the four
    # "spacing 2.00" paragraphs set directly
    assert {"276", "480"} <= lines


# --- Task 12: table alignment ------------------------------------------------

def test_table_alignment_survives(ingest_real):
    """A right-aligned table came out left-aligned; <w:jc> is never emitted."""
    blueprint, _ = ingest_real("formatting")
    document = render_raw_xml(blueprint)

    aligned = [
        element for element in document.iter(f"{W}tblPr")
        if element.find(f"{W}jc") is not None
    ]
    values = Counter(element.find(f"{W}jc").get(f"{W}val") for element in aligned)
    assert values["right"] == 2     # the half-width table and the one beside it


# --- Task 22 (post-1.0): placeholders split by a paragraph break -------------

@pytest.mark.xfail(strict=True, reason="Task 22 — deferred post-1.0 ergonomics")
def test_a_placeholder_split_by_a_paragraph_break_resolves(ingest_real):
    """Writing a grouped placeholder across Enter presses.

    Shift+Enter already works (see above), so this is convenience, not correctness.
    """

    blueprint, diagnostics = ingest_real("languages_invalid", primary="ENG", secondary="UKR")

    assert "unclosed_placeholder" not in codes(diagnostics)
    assert "{{ date" not in "".join(texts(blueprint))


# --- found while landing tasks 5-9 --------------------------------------------

def test_a_header_containing_a_table_ingests(tmp_path, fixture_provider):
    """The header/footer path called normalize_table() without its diagnostics
    argument, so any template with a table in a header or footer failed to import."""
    from docx import Document
    from docx.shared import Inches
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    document = Document()
    document.add_paragraph("Body")
    table = document.sections[0].header.add_table(1, 2, Inches(6))
    table.cell(0, 0).text = "{{ org_name }}"
    table.cell(0, 1).text = "Header"
    path = tmp_path / "header_table.docx"
    document.save(path)

    result = TemplateIngestionPipeline(fixture_provider).ingest(path)

    assert not result.diagnostics.has_errors


def test_a_blueprint_stored_before_title_page_existed_still_loads(ingest_real):
    """Every blueprint already in a user's database predates `title_page` and
    `engine_version`. A new field without a default makes all of them unloadable."""
    from app.document_engine.blueprint.serialize import dump_blueprint, load_blueprint

    blueprint, _ = ingest_real("empty")
    sections, placeholder_defs, config, document = dump_blueprint(blueprint)
    for section in sections:
        del section["style"]["title_page"]
    del config["engine_version"]

    loaded = load_blueprint(sections, placeholder_defs, config, document)

    assert all(section.style.title_page is False for section in loaded.sections)
    assert loaded.config.engine_version == 0


# --- tasks 10-12: cases the fixtures do not isolate ---------------------------

def _ingest_docx(path, provider):
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    pipeline = TemplateIngestionPipeline(provider)
    return pipeline.finalize(pipeline.ingest(path).draft)


def test_run_parts_split_on_hard_breaks_only():
    """A soft break stays text, since a placeholder may span one."""
    from app.document_engine.enums.enums import BreakType
    from app.document_engine.parser.extractors.runs import extract_run_parts

    run = etree.fromstring(
        f'<w:r xmlns:w="{W[1:-1]}"><w:t>a</w:t><w:br/><w:t>b</w:t>'
        f'<w:br w:type="column"/><w:t>c</w:t><w:br w:type="page"/></w:r>'
    )

    assert extract_run_parts(run) == ["a\nb", BreakType.COLUMN, "c", BreakType.PAGE]


def test_a_page_break_keeps_its_place_inside_a_run(tmp_path, fixture_provider):
    """Word writes 'Before', the break and 'After' into a single run."""
    from docx import Document
    from docx.enum.text import WD_BREAK
    from app.document_engine.enums.enums import BreakType

    document = Document()
    run = document.add_paragraph().add_run("Before {{ org_name }}")
    run.add_break(WD_BREAK.PAGE)
    run.add_text("After")
    path = tmp_path / "break.docx"
    document.save(path)

    blueprint = _ingest_docx(path, fixture_provider)
    parts = blueprint.sections[0].blocks[0].segments

    assert [type(s).__name__ for s in parts] == [
        "TextSegment", "PlaceholderSegment", "BreakSegment", "TextSegment",
    ]
    assert parts[2].kind is BreakType.PAGE

    paragraph = render_raw_xml(blueprint).find(f"{W}body/{W}p")
    order = [
        ("br", child.get(f"{W}type")) if child.tag == f"{W}br" else ("t", child.text)
        for run_ in paragraph.iter(f"{W}r")
        for child in run_
        if child.tag in (f"{W}t", f"{W}br")
    ]
    assert order == [("t", "Before "), ("t", "{{ org_name }}"), ("br", "page"), ("t", "After")]


def test_page_break_before_survives(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("First")
    document.add_paragraph("Second").paragraph_format.page_break_before = True
    path = tmp_path / "page_break_before.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")
    flags = [p.find(f"{W}pPr/{W}pageBreakBefore") is not None for p in body.findall(f"{W}p")]

    assert flags == [False, True]


def test_an_explicitly_false_page_break_before_is_not_emitted(ingest_real):
    """formatting.docx carries <w:pageBreakBefore w:val="0"/> on 76 paragraphs.
    Read as true, every one of them would start a new page."""

    document = render_raw_xml(ingest_real("formatting")[0])

    assert document.find(f".//{W}pageBreakBefore") is None


ON_OFF_VALUES = [
    ("1", True), ("true", True), ("on", True),
    ("0", False), ("false", False), ("off", False),
]


@pytest.mark.parametrize("val, expected", [(None, True), *ON_OFF_VALUES])
def test_an_on_off_property_follows_st_onoff(val, expected):
    """Google Docs writes w:val="0"; LibreOffice writes "false". A bare element is on."""
    from app.document_engine.parser.utils.get_attribute import get_bool_prop

    attr = f' w:val="{val}"' if val is not None else ""
    ppr = etree.fromstring(f'<w:pPr xmlns:w="{W[1:-1]}"><w:pageBreakBefore{attr}/></w:pPr>')

    assert get_bool_prop(ppr, "w:pageBreakBefore") is expected
    assert get_bool_prop(ppr, "w:keepNext") is None, "absent is unset, not off"


@pytest.mark.parametrize("val, expected", [(None, None), *ON_OFF_VALUES])
def test_an_on_off_attribute_follows_st_onoff(val, expected):
    from app.document_engine.parser.utils.get_attribute import get_bool_attr

    attr = f' w:sep="{val}"' if val is not None else ""
    cols = etree.fromstring(f'<w:cols xmlns:w="{W[1:-1]}"{attr}/>')

    assert get_bool_attr(cols, "sep") is expected


def test_a_title_page_switched_off_is_off(tmp_path, fixture_provider):
    """titlePg had its own reading, which missed "off"."""
    from docx import Document

    document = Document()
    document.add_paragraph("body")
    document.sections[0].different_first_page_header_footer = True
    document.sections[0]._sectPr.find(f"{W}titlePg").set(f"{W}val", "off")
    path = tmp_path / "title_page_off.docx"
    document.save(path)

    assert _ingest_docx(path, fixture_provider).sections[0].style.title_page is False


def test_a_default_style_marked_true_is_the_default(tmp_path, fixture_provider):
    """w:default on a style is ST_OnOff too; reading only "1" lost the Normal style,
    and with it the spacing and font every unstyled paragraph inherits."""
    from docx import Document

    document = Document()
    normal = document.styles["Normal"]
    normal.paragraph_format.line_spacing = 1.5         # python-docx's docDefaults already say 1.15
    normal.element.set(f"{W}default", "true")
    document.add_paragraph("Body")
    path = tmp_path / "default_true.docx"
    document.save(path)

    spacing = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body/{W}p/{W}pPr/{W}spacing")

    assert spacing.get(f"{W}line") == "360"


@pytest.mark.parametrize("val, expected", [("start", "left"), ("end", "right"), ("center", "center")])
def test_start_and_end_alignments_read_as_left_and_right(val, expected):
    """Unmapped, start/end reach the enum and raise a bare ValueError mid-import."""
    from app.document_engine.parser.extractors.styles import (
        extract_paragraph_style, extract_table_style,
    )

    namespace = f'xmlns:w="{W[1:-1]}"'
    ppr = etree.fromstring(f'<w:pPr {namespace}><w:jc w:val="{val}"/></w:pPr>')
    tbl_pr = etree.fromstring(f'<w:tblPr {namespace}><w:jc w:val="{val}"/></w:tblPr>')

    assert extract_paragraph_style(ppr).alignment == expected
    assert extract_table_style(tbl_pr).alignment == expected


def test_line_spacing_is_inherited_from_the_normal_style(tmp_path, fixture_provider):
    """Word keeps body spacing on the Normal style. A paragraph without a pStyle
    uses it — exactly as runs already inherit its font size."""
    from docx import Document

    document = Document()
    document.styles["Normal"].paragraph_format.line_spacing = 1.15
    document.add_paragraph("Body")
    path = tmp_path / "normal_spacing.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")
    spacing = body.find(f"{W}p/{W}pPr/{W}spacing")

    assert (spacing.get(f"{W}line"), spacing.get(f"{W}lineRule")) == ("276", "auto")


def test_table_jc_sits_where_the_schema_puts_it(ingest_real):
    """CT_TblPr is ordered: jc directly after tblW. Out of order, Word may refuse the file."""
    document = render_raw_xml(ingest_real("formatting")[0])

    for tbl_pr in document.iter(f"{W}tblPr"):
        names = [etree.QName(child).localname for child in tbl_pr]
        assert names.index("jc") == names.index("tblW") + 1


# --- tabs --------------------------------------------------------------------

def run_contents(body) -> list[str]:
    """Run children in order: text as its own string, anything else by tag name."""

    return [
        child.text if child.tag == f"{W}t" else etree.QName(child).localname
        for run in body.iter(f"{W}r")
        for child in run
        if child.tag != f"{W}rPr"
    ]


def test_a_tab_is_emitted_as_an_element(tmp_path, fixture_provider):
    """A tab character inside <w:t> is only whitespace to Word, which drops it.
    A tab has to be <w:tab/> — text falling back from a placeholder showed this."""

    from docx import Document

    document = Document()
    run = document.add_paragraph().add_run("before")
    run.add_tab()
    run.add_text("after")
    path = tmp_path / "tabbed.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")

    assert run_contents(body) == ["before", "tab", "after"]


def test_tabs_survive_in_text_a_placeholder_fell_back_to(tmp_path, fixture_provider):
    """An unclosed placeholder renders literally — tabs included."""

    from docx import Document

    document = Document()
    run = document.add_paragraph().add_run("{{ org_name")
    run.add_tab()
    run.add_text("unclosed")
    path = tmp_path / "fallback.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")

    assert run_contents(body) == ["{{ org_name", "tab", "unclosed"]


def test_a_tab_and_a_line_break_in_one_run_keep_their_order(tmp_path, fixture_provider):
    """Both are elements, so the split has to interleave them, not do one then the other."""

    from docx import Document

    document = Document()
    run = document.add_paragraph().add_run("a")
    run.add_tab()
    run.add_text("b")
    run.add_break()
    run.add_tab()
    run.add_text("c")
    path = tmp_path / "tab_and_break.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")

    assert run_contents(body) == ["a", "tab", "b", "br", "tab", "c"]


# --- Task 16: images in headers and footers ----------------------------------

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


class BundleAssets:
    """An AssetProvider over an ingestion bundle, so rendering keeps the images."""

    def __init__(self, bundle):
        self._bundle = bundle

    def get(self, asset_id):
        from app.document_engine.rendering.ports import Asset

        blob = self._bundle.get(asset_id)
        return Asset(data=blob.data, mime=blob.mime_type) if blob is not None else None


def real_provider():
    from app.document_engine.blueprint.models.template import TemplateConfig
    from tests.conftest import FixtureInputProvider, real_placeholder_defaults

    return FixtureInputProvider(
        placeholders=real_placeholder_defaults(),
        config=TemplateConfig(
            primary_language="ENG", secondary_language=None, type="invoice",
            name="template", description="", append_currency=True,
        ),
    )


def ingest_with_assets(path, provider):
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    pipeline = TemplateIngestionPipeline(provider)
    result = pipeline.ingest(path)
    return pipeline.finalize(result.draft), result


def _images(blocks):
    from app.document_engine.blueprint.models.segment import ImageSegment

    for block in blocks:
        if isinstance(block, ParagraphBlueprint):
            yield from (s for s in block.segments if isinstance(s, ImageSegment))
        elif isinstance(block, TableBlueprint):
            for row in block.rows:
                for cell in row.cells:
                    if isinstance(cell, CellBlueprint):
                        yield from _images(cell.blocks)


def header_footer_images(blueprint):
    return [
        image
        for section in blueprint.sections
        for group in (section.headers, section.footers)
        for hf in (group.default, group.first, group.even)
        if hf is not None
        for image in _images(hf.blocks)
    ]


def body_images(blueprint):
    return [image for section in blueprint.sections for image in _images(section.blocks)]


def test_a_footer_image_resolves_through_the_footers_own_relationships(real_template):
    """layout.docx's footer shows the body's picture, as rId1 in footer1.xml.rels.
    Through document.xml.rels, rId1 is the theme, which got stored as an "image"."""

    blueprint, result = ingest_with_assets(real_template("layout"), real_provider())
    (footer_image,) = header_footer_images(blueprint)

    # both reference word/media/image1.jpg, so they must be the same asset
    assert footer_image.asset_id in {image.asset_id for image in body_images(blueprint)}
    # the bundle also holds the template's embedded fonts, so only the picture is checked
    assert result.assets[footer_image.asset_id].mime_type.startswith("image/")


def test_a_footer_image_reaches_the_rendered_footer(real_template):
    """End of the chain: the footer part holds a picture, resolved through its own
    relationships, and the bytes behind it are a JPEG."""

    import re

    blueprint, result = ingest_with_assets(real_template("layout"), real_provider())
    docx = TemplateRenderingPipeline(BundleAssets(result.assets)).render_raw(blueprint).docx

    pictures = []
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        for name in archive.namelist():
            if not re.fullmatch(r"word/footer\d+\.xml", name):
                continue
            rids = [blip.get(R_EMBED) for blip in etree.fromstring(archive.read(name)).iter(f"{A}blip")]
            if not rids:
                continue
            rels = etree.fromstring(archive.read(f"word/_rels/{name.rsplit('/', 1)[-1]}.rels"))
            targets = {relationship.get("Id"): relationship.get("Target") for relationship in rels}
            pictures += [archive.read(f"word/{targets[rid]}")[:2] for rid in rids]

    assert pictures == [b"\xff\xd8"]        # one JPEG


def test_a_header_gets_its_own_picture_not_the_bodys(tmp_path, fixture_provider):
    """Relationship ids are per part, so they collide across parts. Whatever the
    ids, a header's picture must be the header's picture."""

    from docx import Document
    from PIL import Image

    body_png, header_png = tmp_path / "body.png", tmp_path / "header.png"
    Image.new("RGB", (8, 8), "red").save(body_png)
    Image.new("RGB", (8, 8), "blue").save(header_png)

    document = Document()
    document.add_picture(str(body_png))
    document.sections[0].header.paragraphs[0].add_run().add_picture(str(header_png))
    path = tmp_path / "pictures.docx"
    document.save(path)

    blueprint, result = ingest_with_assets(path, fixture_provider)
    (header_image,) = header_footer_images(blueprint)

    assert result.assets[header_image.asset_id].data == header_png.read_bytes()


def test_a_relationship_that_is_not_an_image_is_never_read_as_one(tmp_path, fixture_provider):
    """Defence in depth: a picture pointed at the styles part is refused with a
    warning at import, not stored as an "image" that only fails at render."""

    from docx import Document
    from PIL import Image

    png = tmp_path / "body.png"
    Image.new("RGB", (8, 8), "red").save(png)
    document = Document()
    document.add_picture(str(png))
    source = tmp_path / "source.docx"
    document.save(source)

    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
    by_type = {relationship.get("Type").rsplit("/", 1)[-1]: relationship.get("Id") for relationship in rels}
    parts["word/document.xml"] = parts["word/document.xml"].replace(
        f'r:embed="{by_type["image"]}"'.encode(), f'r:embed="{by_type["styles"]}"'.encode(),
    )
    path = tmp_path / "misdirected.docx"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)

    blueprint, result = ingest_with_assets(path, fixture_provider)

    assert body_images(blueprint) == []
    assert "image_relationship_not_an_image" in codes(result.diagnostics)
    assert all(blob.mime_type.startswith("image/") for blob in result.assets.values())


# --- Task 17: page numbers ---------------------------------------------------

def field_runs(paragraph, runs):
    """Append runs from a spec. Each run is a list of children: a str is a <w:t>,
    ("fld", kind) a <w:fldChar>, and ("instr", code) an <w:instrText>."""

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    space = "{http://www.w3.org/XML/1998/namespace}space"
    built = []
    for children in runs:
        run = paragraph.add_run()
        for child in children:
            if isinstance(child, str):
                element = OxmlElement("w:t")
                element.text = child
                element.set(space, "preserve")
            elif child[0] == "fld":
                element = OxmlElement("w:fldChar")
                element.set(qn("w:fldCharType"), child[1])
            else:
                element = OxmlElement("w:instrText")
                element.text = child[1]
                element.set(space, "preserve")
            run._r.append(element)
        built.append(run)
    return built


def emitted_instructions(root) -> list[str]:
    """Field codes as written, in either form: <w:fldSimple w:instr>, or the
    instrText runs between a begin and a separate."""

    found = [simple.get(f"{W}instr").strip() for simple in root.iter(f"{W}fldSimple")]
    code, inside = [], False
    for element in root.iter(f"{W}fldChar", f"{W}instrText"):
        if element.tag == f"{W}instrText":
            if inside:
                code.append(element.text or "")
        elif element.get(f"{W}fldCharType") == "begin":
            code, inside = [], True
        elif element.get(f"{W}fldCharType") == "separate" and inside:
            found.append("".join(code).strip())
            inside = False
    return found


def field_segments(blueprint):
    # matched by name, so these tests fail on assertions, not an ImportError
    return [s for s in segments(blueprint) if type(s).__name__ == "FieldSegment"]


def test_a_google_docs_page_number_survives_ingestion(ingest_real):
    """Google Docs writes the whole PAGE field into one run, with no result text.
    Ignoring fldChar and instrText left each footer's page-number paragraph empty."""

    blueprint, _ = ingest_real("layout")

    assert [(f.kind, f.instruction) for f in field_segments(blueprint)] == [
        ("PAGE", "PAGE"), ("PAGE", "PAGE"),         # the default footer and the first-page one
    ]


def test_a_page_number_is_written_back_as_a_field(ingest_real):
    import re

    blueprint, _ = ingest_real("layout")
    docx = TemplateRenderingPipeline(NoAssets()).render_raw(blueprint).docx

    instructions = []
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"word/(header|footer)\d+\.xml", name):
                root = etree.fromstring(archive.read(name))
                instructions += emitted_instructions(root)

    assert instructions == ["PAGE", "PAGE"]


def test_a_word_page_x_of_y_stays_live(tmp_path, fixture_provider):
    """Word caches each field's last result as plain text between separate and end.
    Read as text, every page would print "Page 7 of 9" forever."""

    from docx import Document

    document = Document()
    runs = field_runs(document.add_paragraph(), [
        ["Page "],
        [("fld", "begin")], [("instr", " PAGE ")], [("fld", "separate")], ["7"], [("fld", "end")],
        [" of "],
        [("fld", "begin")], [("instr", " NUMPAGES ")], [("fld", "separate")], ["9"], [("fld", "end")],
    ])
    for run in runs[1:6]:
        run.bold = True
    path = tmp_path / "page_x_of_y.docx"
    document.save(path)

    parts = _ingest_docx(path, fixture_provider).sections[0].blocks[0].segments

    assert [(type(s).__name__, getattr(s, "text", None) or getattr(s, "kind", None)) for s in parts] == [
        ("TextSegment", "Page "), ("FieldSegment", "PAGE"),
        ("TextSegment", " of "), ("FieldSegment", "NUMPAGES"),
    ]
    assert parts[1].cached == "7"
    assert parts[1].style.bold, "a field keeps its own formatting"


def test_a_simple_field_survives_with_its_switches(tmp_path, fixture_provider):
    """LibreOffice writes <w:fldSimple>, whose runs sit inside the field, so
    findall("w:r") on the paragraph never saw them. The \\* roman switch has to
    survive too, or page iv prints as 4."""

    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = Document()
    paragraph = document.add_paragraph("Page ")
    simple = OxmlElement("w:fldSimple")
    simple.set(qn("w:instr"), r" PAGE \* roman ")
    run, text = OxmlElement("w:r"), OxmlElement("w:t")
    text.text = "iv"
    run.append(text)
    simple.append(run)
    paragraph._p.append(simple)
    path = tmp_path / "simple_field.docx"
    document.save(path)

    blueprint = _ingest_docx(path, fixture_provider)
    emitted = emitted_instructions(render_raw_xml(blueprint))

    assert [(f.kind, f.instruction, f.cached) for f in field_segments(blueprint)] == [
        ("PAGE", r"PAGE \* roman", "iv"),
    ]
    assert emitted == [r"PAGE \* roman"]


def test_a_field_code_split_mid_word_still_reads(tmp_path, fixture_provider):
    """Word splits instrText wherever an edit landed: ' PA' + 'GE '."""

    from docx import Document

    document = Document()
    field_runs(document.add_paragraph(), [
        [("fld", "begin")], [("instr", " PA")], [("instr", "GE ")], [("fld", "separate")],
        ["3"], [("fld", "end")],
    ])
    path = tmp_path / "split_code.docx"
    document.save(path)

    assert [f.kind for f in field_segments(_ingest_docx(path, fixture_provider))] == ["PAGE"]


def test_an_unsupported_field_keeps_the_text_it_showed(tmp_path, fixture_provider):
    """Only page fields are recomputed. Anything else — a date, a cross-reference —
    keeps what it last showed, and says so at import."""

    from docx import Document
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    document = Document()
    field_runs(document.add_paragraph(), [
        ["Issued "],
        [("fld", "begin")], [("instr", ' DATE \\@ "dd.MM.yyyy" ')], [("fld", "separate")],
        ["24.09.2026"], [("fld", "end")],
    ])
    path = tmp_path / "date_field.docx"
    document.save(path)

    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(path)

    assert "".join(texts(pipeline.finalize(result.draft))) == "Issued 24.09.2026"
    assert "field_kept_as_text" in codes(result.diagnostics)


# --- Task 24: text inside hyperlinks and other run containers ----------------
#
# Hyperlinks are kept as plain text by design: the output is meant for print
# (agreed with the user's partners 2026-09-24). What must never happen is losing
# the text, which is what skipping the containers did.

LINK_TASK = "Task 24 — added to batch A 2026-09-24"


def _run(text):
    from docx.oxml import OxmlElement

    run, t = OxmlElement("w:r"), OxmlElement("w:t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run.append(t)
    return run


def add_hyperlink(paragraph, url, text):
    """python-docx has no hyperlink API: relate the URL to the paragraph's own
    part (the header's, for a header paragraph) and wrap a run."""

    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
    link.append(_run(text))
    paragraph._p.append(link)


def test_a_hyperlink_is_kept_as_plain_text(tmp_path, fixture_provider):
    """Runs inside <w:hyperlink> were never read at all, so the linked words vanished."""

    from docx import Document

    document = Document()
    add_hyperlink(document.add_paragraph("Visit "), "https://example.com", "our site")
    path = tmp_path / "link.docx"
    document.save(path)

    blueprint = _ingest_docx(path, fixture_provider)
    document_xml = render_raw_xml(blueprint)

    assert "".join(texts(blueprint)) == "Visit our site"
    assert document_xml.find(f".//{W}hyperlink") is None, "plain text, by design"


def test_a_placeholder_inside_a_hyperlink_still_resolves(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    add_hyperlink(document.add_paragraph(), "mailto:billing@example.com", "{{ org_name }}")
    path = tmp_path / "linked_placeholder.docx"
    document.save(path)

    assert [p.key for p in placeholders(_ingest_docx(path, fixture_provider))] == ["org_name"]


def test_the_text_of_a_header_hyperlink_survives(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("Body")
    add_hyperlink(document.sections[0].header.paragraphs[0], "https://example.com/terms", "Terms")
    path = tmp_path / "header_link.docx"
    document.save(path)

    header = _ingest_docx(path, fixture_provider).sections[-1].headers.default

    assert [s.text for block in header.blocks for s in block.segments] == ["Terms"]


def test_a_hyperlink_field_is_plain_text_without_a_warning(tmp_path, fixture_provider):
    """Word's field form of a link already kept its text; once plain text is the
    intended outcome, warning about it is noise."""

    from docx import Document
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline

    document = Document()
    field_runs(document.add_paragraph(), [
        [("fld", "begin")], [("instr", ' HYPERLINK "https://example.com" ')], [("fld", "separate")],
        ["example.com"], [("fld", "end")],
    ])
    path = tmp_path / "hyperlink_field.docx"
    document.save(path)

    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(path)

    assert "".join(texts(pipeline.finalize(result.draft))) == "example.com"
    assert "field_kept_as_text" not in codes(result.diagnostics)


def test_an_internal_link_keeps_its_text(tmp_path, fixture_provider):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = Document()
    link = OxmlElement("w:hyperlink")
    link.set(qn("w:anchor"), "terms")
    link.append(_run("see terms"))
    document.add_paragraph()._p.append(link)
    path = tmp_path / "anchor.docx"
    document.save(path)

    assert "".join(texts(_ingest_docx(path, fixture_provider))) == "see terms"


def test_content_controls_and_insertions_are_read_but_deletions_are_not(tmp_path, fixture_provider):
    """Word wraps runs in these too. A tracked deletion is the one that must stay out."""

    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = Document()
    paragraph = document.add_paragraph()._p
    control, content = OxmlElement("w:sdt"), OxmlElement("w:sdtContent")
    content.append(_run("Control "))
    control.append(content)
    paragraph.append(control)

    for tag, text in (("w:ins", "inserted"), ("w:del", " deleted")):
        change = OxmlElement(tag)
        change.set(qn("w:id"), "1")
        change.set(qn("w:author"), "test")
        if tag == "w:del":
            run, gone = OxmlElement("w:r"), OxmlElement("w:delText")
            gone.text = text
            run.append(gone)
        else:
            run = _run(text)
        change.append(run)
        paragraph.append(change)

    path = tmp_path / "containers.docx"
    document.save(path)

    assert "".join(texts(_ingest_docx(path, fixture_provider))) == "Control inserted"


# --- found 2026-09-24: the settings part's relationship type ------------------

def test_even_page_headers_relate_settings_with_a_relationship_type(tmp_path, fixture_provider):
    """Word reads w:evenAndOddHeaders only from a settings part related as
    .../relationships/settings. Related with its *content type* instead, the part
    is ignored, so even-page headers never appeared."""

    from docx import Document

    document = Document()
    document.settings.odd_and_even_pages_header_footer = True
    document.add_paragraph("Body")
    document.sections[0].even_page_header.paragraphs[0].text = "Even page"
    path = tmp_path / "even_headers.docx"
    document.save(path)

    docx = TemplateRenderingPipeline(NoAssets()).render_raw(_ingest_docx(path, fixture_provider)).docx
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        rels = etree.fromstring(archive.read("word/_rels/document.xml.rels"))

    assert {r.get("Target"): r.get("Type") for r in rels}.get("settings.xml") == (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
    )


# --- Task 13: run formatting -------------------------------------------------

# CT_RPr is an xsd:sequence; Word refuses a run whose properties are out of order
CT_RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
    "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish",
    "webHidden", "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight",
    "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang",
    "eastAsianLayout", "specVanish", "oMath",
]


def style_of(segment, attribute):
    # getattr twice: images and breaks have no style, and today's styles lack the field
    return getattr(getattr(segment, "style", None), attribute, None)


def test_placeholders_inherit_the_run_formatting_around_them(ingest_real):
    """formatting.docx writes each formatting line as one run, placeholders and all.
    The values must render struck through, in small caps, raised or lowered too."""

    blueprint, _ = ingest_real("formatting")

    def keys_where(attribute, value):
        return sorted({p.key for p in placeholders(blueprint) if style_of(p, attribute) == value})

    line = ["client_bank_info", "client_bank_name", "client_name", "client_type", "date", "prefix"]
    assert keys_where("strike", True) == line
    assert keys_where("small_caps", True) == line
    assert keys_where("script", "superscript") == line
    assert keys_where("script", "subscript") == line


def test_highlight_survives_ingestion(ingest_real):
    """Google Docs writes text highlight as a named <w:highlight>; layout.docx uses yellow."""

    blueprint, _ = ingest_real("layout")

    assert {style_of(s, "highlight") for s in segments(blueprint)} - {None} == {"yellow"}


@pytest.mark.parametrize("name, expected", [
    ("formatting", {"strike", "smallCaps", "vertAlign"}),
    ("layout", {"highlight"}),
])
def test_run_formatting_is_written_back_in_schema_order(name, expected, ingest_real):
    document = render_raw_xml(ingest_real(name)[0])

    seen = set()
    for rpr in document.iter(f"{W}rPr"):
        names = [etree.QName(child).localname for child in rpr]
        positions = [CT_RPR_ORDER.index(child) for child in names]
        assert positions == sorted(positions), names
        seen.update(names)

    assert expected <= seen


def test_an_explicit_no_underline_is_not_underlined(tmp_path, fixture_provider):
    """w:u names an underline style; "none" means none. That includes switching off
    the underline a character style sets, which is what a template author does to
    un-underline one word."""

    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE

    document = Document()
    underlined = document.styles.add_style("Underlined", WD_STYLE_TYPE.CHARACTER)
    underlined.font.underline = True
    paragraph = document.add_paragraph()
    plain = paragraph.add_run("plain ")
    plain.font.underline = False
    styled = paragraph.add_run("{{ org_name }}")
    styled.style = underlined
    styled.font.underline = False
    path = tmp_path / "no_underline.docx"
    document.save(path)

    assert [s.style.underline for s in segments(_ingest_docx(path, fixture_provider))] == [False, False]


def test_a_double_strikethrough_is_struck_through(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph().add_run("void").font.double_strike = True
    path = tmp_path / "double_strike.docx"
    document.save(path)

    assert [style_of(s, "strike") for s in segments(_ingest_docx(path, fixture_provider))] == [True]


# --- Task 19: horizontal rules and paragraph borders -------------------------

# CT_PPr is an xsd:sequence as well
CT_PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
    "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
    "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
    "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
    "mirrorIndents", "suppressOverlap", "jc", "textDirection", "textAlignment",
    "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
]

XMLNS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office"'
)


def fragment(xml: str) -> etree._Element:
    return etree.fromstring(f"<root {XMLNS}>{xml}</root>")[0]


def pbdr(**sides) -> etree._Element:
    """<w:pBdr> from side=(val, sz, space, color)."""
    return fragment("<w:pBdr>" + "".join(
        f'<w:{side} w:val="{val}" w:sz="{sz}" w:space="{space}" w:color="{color}"/>'
        for side, (val, sz, space, color) in sides.items()
    ) + "</w:pBdr>")


def rule(height="1.5pt", fill="#A0A0A0") -> etree._Element:
    """A run holding a VML horizontal rule, as Google Docs writes one."""
    return fragment(
        f'<w:r><w:pict><v:rect style="width:0.0pt;height:{height}" o:hr="t" o:hrstd="t" '
        f'o:hralign="center" fillcolor="{fill}" stroked="f"/></w:pict></w:r>'
    )


def borders_of(blueprint) -> list[dict]:
    return [
        block.style.borders.model_dump(mode="json", exclude_none=True)
        for block in _blocks(blueprint)
        if isinstance(block, ParagraphBlueprint) and getattr(block.style, "borders", None) is not None
    ]


def seed_template(name):
    from app.db.seed import SEED_DIR

    return SEED_DIR / "templates" / f"{name}.docx"


GOOGLE_RULE = {"bottom": {"style": "single", "size": 12, "space": 0, "color": "A0A0A0"}}
UKR_BORDER = {"bottom": {"style": "single", "size": 8, "space": 0, "color": "000000"}}


def test_google_docs_nil_borders_draw_nothing(ingest_real):
    """Google Docs writes an all-nil <w:pBdr> on 76 of formatting.docx's paragraphs.
    nil means no border; carried along, every paragraph would come out boxed."""

    blueprint, _ = ingest_real("formatting")

    assert borders_of(blueprint) == []
    assert render_raw_xml(blueprint).find(f".//{W}pBdr") is None


def test_a_horizontal_rule_becomes_a_bottom_border(ingest_real):
    """layout.docx's Insert > Horizontal line is a VML shape the parser never read."""

    assert borders_of(ingest_real("layout")[0]) == [GOOGLE_RULE]


@pytest.mark.parametrize("name, expected", [
    ("DEFAULT_ENG_invoice", GOOGLE_RULE),
    ("DEFAULT_UKR_invoice", UKR_BORDER),
    ("DEFAULT_UKR_akt_nadanykh_posluh", UKR_BORDER),
])
def test_a_shipped_template_keeps_its_rule(name, expected):
    """Three of the four built-ins draw a line under the header block: the English
    one with a horizontal rule, the Ukrainian ones with a paragraph border."""

    document = render_raw_xml(ingest_with_assets(seed_template(name), real_provider())[0])
    emitted = [
        {etree.QName(side).localname: {
            "style": side.get(f"{W}val"), "size": int(side.get(f"{W}sz")),
            "space": int(side.get(f"{W}space")), "color": side.get(f"{W}color"),
        } for side in borders}
        for borders in document.iter(f"{W}pBdr")
    ]

    assert emitted == [expected]


def test_paragraph_borders_are_written_in_schema_order(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    paragraph = document.add_paragraph("Boxed")
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.page_break_before = True
    paragraph.paragraph_format.space_after = 120
    paragraph._p.get_or_add_pPr().append(pbdr(
        between=("single", 4, 1, "auto"), right=("dotted", 4, 4, "00FF00"),
        bottom=("double", 6, 1, "0000FF"), left=("dashed", 4, 4, "FF0000"),
        top=("single", 8, 1, "000000"),
    ))
    path = tmp_path / "boxed.docx"
    document.save(path)

    ppr = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f".//{W}pPr")
    names = [etree.QName(child).localname for child in ppr]
    borders = ppr.find(f"{W}pBdr")

    assert "pBdr" in names
    assert [CT_PPR_ORDER.index(n) for n in names] == sorted(CT_PPR_ORDER.index(n) for n in names), names
    assert [etree.QName(side).localname for side in borders] == ["top", "left", "bottom", "right", "between"]
    assert [(s.get(f"{W}val"), s.get(f"{W}sz"), s.get(f"{W}space"), s.get(f"{W}color")) for s in borders] == [
        ("single", "8", "1", "000000"), ("dashed", "4", "4", "FF0000"), ("double", "6", "1", "0000FF"),
        ("dotted", "4", "4", "00FF00"), ("single", "4", "1", "auto"),
    ]


def test_each_side_is_inherited_from_the_style_and_can_be_switched_off(tmp_path, fixture_provider):
    """Word's Title style carries a bottom border. A paragraph inherits each side on
    its own, and a nil side switches the style's one off, which is what the all-nil
    <w:pBdr> Google Docs writes does to a styled paragraph."""

    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE

    document = Document()
    ruled = document.styles.add_style("Ruled", WD_STYLE_TYPE.PARAGRAPH)
    ruled.element.get_or_add_pPr().append(pbdr(top=("single", 4, 1, "111111"), bottom=("single", 8, 4, "4F81BD")))

    document.add_paragraph("styled", style=ruled)
    document.add_paragraph("top off", style=ruled)._p.get_or_add_pPr().append(pbdr(top=("nil", 0, 0, "auto")))
    document.add_paragraph("plus left", style=ruled)._p.get_or_add_pPr().append(pbdr(left=("single", 4, 4, "222222")))
    document.add_paragraph("all off", style=ruled)._p.get_or_add_pPr().append(pbdr(**{
        side: ("nil", 0, 0, "auto") for side in ("top", "left", "bottom", "right", "between")
    }))
    path = tmp_path / "inherited.docx"
    document.save(path)

    top = {"style": "single", "size": 4, "space": 1, "color": "111111"}
    bottom = {"style": "single", "size": 8, "space": 4, "color": "4F81BD"}
    left = {"style": "single", "size": 4, "space": 4, "color": "222222"}

    assert borders_of(_ingest_docx(path, fixture_provider)) == [
        {"top": top, "bottom": bottom},
        {"bottom": bottom},
        {"top": top, "left": left, "bottom": bottom},
    ]


def test_an_unsupported_border_style_prints_as_a_plain_line(tmp_path, fixture_provider):
    """ST_Border has some 190 values, most of them art borders. One the engine does
    not know is drawn as a single line rather than blocking the import."""

    from docx import Document

    document = Document()
    document.add_paragraph("embossed")._p.get_or_add_pPr().append(pbdr(bottom=("threeDEmboss", 24, 1, "auto")))
    path = tmp_path / "emboss.docx"
    document.save(path)

    assert borders_of(_ingest_docx(path, fixture_provider)) == [
        {"bottom": {"style": "single", "size": 24, "space": 1, "color": "auto"}},
    ]


@pytest.mark.parametrize("height, fill, size, color", [
    ("1.5pt", "#A0A0A0", 12, "A0A0A0"),     # Google Docs' own
    ("3pt", "#ff0000", 24, "FF0000"),
    ("4px", "black", 24, "A0A0A0"),         # 4px is 3pt; a color name falls back to Word's grey
    ("40pt", "#000000", 96, "000000"),      # clamped to Word's widest line border
])
def test_a_rule_keeps_its_height_and_color(height, fill, size, color, tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph()._p.append(rule(height, fill))
    path = tmp_path / "rule.docx"
    document.save(path)

    assert borders_of(_ingest_docx(path, fixture_provider)) == [
        {"bottom": {"style": "single", "size": size, "space": 0, "color": color}},
    ]


def test_a_rule_neither_overrides_a_border_nor_survives_deletion(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    bordered = document.add_paragraph()
    bordered._p.get_or_add_pPr().append(pbdr(bottom=("double", 6, 1, "0000FF")))
    bordered._p.append(rule())
    deleted = fragment('<w:del w:id="1" w:author="a" w:date="2026-01-01T00:00:00Z"/>')
    deleted.append(rule())
    document.add_paragraph()._p.append(deleted)
    path = tmp_path / "rules.docx"
    document.save(path)

    assert borders_of(_ingest_docx(path, fixture_provider)) == [
        {"bottom": {"style": "double", "size": 6, "space": 1, "color": "0000FF"}},
    ]


# --- Task 20: vertically merged cells ----------------------------------------

# CT_TcPr is an xsd:sequence too
CT_TCPR_ORDER = [
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap",
    "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark", "headers",
    "cellIns", "cellDel", "cellMerge", "tcPrChange",
]


def merge_map(table) -> list[list[tuple[int, str]]]:
    """Per row, (grid column, vMerge value) of every merged cell. A merge follows
    the grid column, not the cell index, so spans have to be counted."""

    rows = []
    for tr in table.findall(f"{W}tr"):
        row, column = [], 0
        for tc in tr.findall(f"{W}tc"):
            span = tc.find(f"{W}tcPr/{W}gridSpan")
            merge = tc.find(f"{W}tcPr/{W}vMerge")
            if merge is not None:
                row.append((column, merge.get(f"{W}val", "continue")))
            column += int(span.get(f"{W}val")) if span is not None else 1
        rows.append(row)
    return rows


def merged_tables(document) -> list:
    return [t for t in document.iter(f"{W}tbl") if t.find(f".//{W}vMerge") is not None]


def cell_texts(table, column_index) -> list[str]:
    return ["".join(t.text or "" for t in tr.findall(f"{W}tc")[column_index].iter(f"{W}t"))
            for tr in table.findall(f"{W}tr")]


def test_merged_cells_survive(ingest_real):
    """formatting.docx merges a placeholder cell down three rows and a text cell
    down two, in a table whose other rows use gridSpan, so cell 5 of the first row
    and cell 4 of the next are the same grid column."""

    merged = merged_tables(render_raw_xml(ingest_real("formatting")[0]))

    assert [merge_map(table) for table in merged] == [[
        [(6, "restart"), (7, "restart")],
        [(6, "continue"), (7, "continue")],
        [(6, "continue")],
    ]]


def test_vmerge_is_written_in_schema_order(ingest_real):
    document = render_raw_xml(ingest_real("formatting")[0])

    seen = set()
    for tcpr in document.iter(f"{W}tcPr"):
        names = [etree.QName(child).localname for child in tcpr]
        positions = [CT_TCPR_ORDER.index(name) for name in names]
        assert positions == sorted(positions), names
        seen.update(names)

    assert "vMerge" in seen


def test_a_merge_starting_in_an_invoice_line_row_is_split(ingest_real):
    """That row repeats once per line, so every copy would restart the merge and
    only the last one would reach the rows below. formatting.docx does this three
    times; splitting keeps what the engine always did there, and says so."""

    blueprint, diagnostics = ingest_real("formatting")
    document = render_values_xml(blueprint, every_value_context(blueprint))

    assert codes(diagnostics).count("vertical_merge_in_repeated_row") == 3
    assert len(merged_tables(document)) == 1, "only the table without invoice lines keeps its merges"


def test_a_label_merged_down_beside_invoice_lines_spans_every_line(tmp_path):
    """The merge starts above the repeated row, so each copy continues it. Word
    and python-docx write the continuation as a bare <w:vMerge/>, with no val."""

    from docx import Document

    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Services"
    table.cell(0, 1).text = "Description"
    table.cell(1, 1).text = "{{ invl_desc }}"
    table.cell(0, 0).merge(table.cell(1, 0))
    path = tmp_path / "label.docx"
    document.save(path)

    blueprint, result = ingest_with_assets(path, real_provider())
    rendered = next(render_values_xml(blueprint, every_value_context(blueprint)).iter(f"{W}tbl"))

    assert merge_map(rendered) == [[(0, "restart")], [(0, "continue")], [(0, "continue")]]
    assert cell_texts(rendered, 0) == ["Services", "", ""]
    assert cell_texts(rendered, 1) == ["Description", "<invl_desc>", "<invl_desc>"]
    assert "vertical_merge_in_repeated_row" not in codes(result.diagnostics)


# --- Task 15: page color ----------------------------------------------------

def render_raw_docx(blueprint) -> bytes:
    result = TemplateRenderingPipeline(NoAssets()).render_raw(blueprint)
    assert result.docx is not None
    return result.docx


def page_color(docx: bytes) -> tuple[str | None, bool]:
    """(the <w:background> color, whether settings.xml tells Word to show it)."""

    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        settings = etree.fromstring(archive.read("word/settings.xml")) \
            if "word/settings.xml" in archive.namelist() else None

    background = document.find(f"{W}background")
    shown = settings is not None and settings.find(f"{W}displayBackgroundShape") is not None
    return (background.get(f"{W}color") if background is not None else None), shown


def with_background(document, color: str):
    """<w:background> is the first child of <w:document>; python-docx has no API for it."""
    document.element.insert(0, fragment(f'<w:background w:color="{color}"/>'))


def test_a_page_color_survives(ingest_real):
    """formatting.docx is pink. Word shows a page color only when settings.xml
    carries <w:displayBackgroundShape/>, so that has to come along."""

    docx = render_raw_docx(ingest_real("formatting")[0])

    assert page_color(docx) == ("F4CCCC", True)
    assert etree.QName(_document_xml(docx)[0]).localname == "background", "CT_Document puts it before the body"


def test_a_template_without_a_page_color_gets_none(fixture_provider):
    """The Ukrainian built-ins were not written by Google Docs and have none."""

    blueprint, _ = ingest_with_assets(seed_template("DEFAULT_UKR_invoice"), real_provider())

    assert page_color(render_raw_docx(blueprint)) == (None, False)


def test_an_automatic_page_color_is_no_color(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("auto")
    with_background(document, "auto")
    path = tmp_path / "auto.docx"
    document.save(path)

    assert page_color(render_raw_docx(_ingest_docx(path, fixture_provider))) == (None, False)


def test_a_page_color_and_even_headers_share_settings_in_schema_order(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("body")
    document.settings.odd_and_even_pages_header_footer = True
    document.sections[0].even_page_header.paragraphs[0].text = "even"
    with_background(document, "ddeeff")
    path = tmp_path / "even_and_color.docx"
    document.save(path)

    docx = render_raw_docx(_ingest_docx(path, fixture_provider))
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        settings = etree.fromstring(archive.read("word/settings.xml"))

    assert page_color(docx) == ("DDEEFF", True), "hex is upper-cased"
    assert [etree.QName(child).localname for child in settings] == ["displayBackgroundShape", "evenAndOddHeaders"]


def test_a_page_color_is_stored_replaced_and_copied(session, real_template):
    """Blueprints are stored across columns, and the document-level part has one of
    its own. Every write path must carry it: create, replace (rebuild) and copy,
    which copies the columns one by one."""

    from app.services.template.repository import TemplateRepository

    white, white_result = ingest_with_assets(real_template("empty"), real_provider())
    pink, pink_result = ingest_with_assets(real_template("formatting"), real_provider())

    repo = TemplateRepository(session)
    template_id = repo.create(white, white_result.assets, white_result.source)
    created = repo.get_blueprint(template_id)

    repo.replace_blueprint(repo.current_version(template_id).id, pink, pink_result.assets)
    replaced = repo.get_blueprint(template_id)

    copied = repo.get_blueprint(repo.copy(template_id, "Pink copy"))

    backgrounds = [getattr(getattr(bp, "document", None), "background", None) for bp in (created, replaced, copied)]
    assert backgrounds == ["FFFFFF", "F4CCCC", "F4CCCC"]


# --- Task 18: text columns ---------------------------------------------------

# CT_SectPr is an xsd:sequence as well
CT_SECTPR_ORDER = [
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz",
    "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols", "formProt",
    "vAlign", "noEndnote", "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid",
    "printerSettings", "sectPrChange",
]


def section_columns(document) -> list:
    """Per section, in order: None for one column, else (num, [(w, space), ...]) or
    (num, space, sep) for equal columns."""

    out = []
    for sect in document.iter(f"{W}sectPr"):
        cols = sect.find(f"{W}cols")
        if cols is None:
            out.append(None)
        elif cols.findall(f"{W}col"):
            out.append((cols.get(f"{W}num"), [(c.get(f"{W}w"), c.get(f"{W}space")) for c in cols.findall(f"{W}col")]))
        else:
            out.append((cols.get(f"{W}num"), cols.get(f"{W}space"), cols.get(f"{W}sep")))
    return out


def with_columns(document, xml: str):
    """python-docx has no API for text columns; <w:cols> goes into the body's sectPr."""

    sect_pr = document.sections[0]._sectPr
    existing = sect_pr.find(f"{W}cols")
    if existing is not None:
        sect_pr.remove(existing)
    titlepg = sect_pr.find(f"{W}titlePg")
    cols = fragment(xml)
    if titlepg is not None:
        titlepg.addprevious(cols)
    else:
        sect_pr.append(cols)


def test_text_columns_survive(ingest_real):
    """layout.docx switches between one, two and three columns with continuous
    section breaks. Google Docs writes explicit widths, as fractional twips."""

    two = ("2", [("6618", "720"), ("6618", "0")])
    three = ("3", [("4172", "720"), ("4172", "720"), ("4172", "0")])

    assert section_columns(render_raw_xml(ingest_real("layout")[0])) == [two, None, two, three, None]


def test_cols_is_written_in_schema_order(ingest_real):
    document = render_raw_xml(ingest_real("layout")[0])

    seen = set()
    for sect in document.iter(f"{W}sectPr"):
        names = [etree.QName(child).localname for child in sect]
        positions = [CT_SECTPR_ORDER.index(name) for name in names]
        assert positions == sorted(positions), names
        seen.update(names)

    assert "cols" in seen


def test_equal_columns_are_written_as_word_writes_them(tmp_path, fixture_provider):
    """A count and a space, with no <w:col> children; the separator line survives."""

    from docx import Document

    document = Document()
    document.add_paragraph("two columns")
    with_columns(document, '<w:cols w:num="2" w:space="425" w:sep="1"/>')
    path = tmp_path / "equal.docx"
    document.save(path)

    assert section_columns(render_raw_xml(_ingest_docx(path, fixture_provider))) == [("2", "425", "1")]


@pytest.mark.parametrize("xml", [
    '<w:cols w:space="720"/>',                     # Word's own single column
    '<w:cols w:num="1" w:space="720"/>',
])
def test_a_single_column_writes_no_cols(xml, tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("one column")
    with_columns(document, xml)
    path = tmp_path / "single.docx"
    document.save(path)

    assert section_columns(render_raw_xml(_ingest_docx(path, fixture_provider))) == [None]


def test_unusable_explicit_widths_fall_back_to_equal_columns(tmp_path, fixture_provider):
    """Two widths for three columns: Word ignores them and so does the engine."""

    from docx import Document

    document = Document()
    document.add_paragraph("three columns")
    with_columns(document, '<w:cols w:num="3" w:space="360" w:equalWidth="0">'
                           '<w:col w:w="3000" w:space="360"/><w:col w:w="3000" w:space="0"/></w:cols>')
    path = tmp_path / "broken_widths.docx"
    document.save(path)

    assert section_columns(render_raw_xml(_ingest_docx(path, fixture_provider))) == [("3", "360", None)]


def test_a_standalone_invoice_table_fits_its_column(tmp_path):
    """The system table is as wide as the text it sits in. In a two-column section
    that is one column, not the page; a header still spans the whole page."""

    from docx import Document

    document = Document()
    document.add_paragraph("{{ invoice_table }}")
    document.sections[0].header.paragraphs[0].text = "{{ invoice_table }}"
    with_columns(document, '<w:cols w:num="2" w:space="720"/>')
    path = tmp_path / "table_in_columns.docx"
    document.save(path)

    blueprint, _ = ingest_with_assets(path, real_provider())
    section = blueprint.sections[0]
    text_width = section.style.page_width - section.style.margins.left - section.style.margins.right

    body_table = section.blocks[0]
    header_table = section.headers.default.blocks[0]

    assert isinstance(body_table, TablePlaceholder)
    assert body_table.style.width.value == (text_width - 720) // 2
    assert header_table.style.width.value == text_width


# --- Task 14a: first-line indents and the paragraph mark ----------------------

def indents(document) -> set[tuple[str | None, str | None, str | None]]:
    return {(i.get(f"{W}left"), i.get(f"{W}hanging"), i.get(f"{W}firstLine")) for i in document.iter(f"{W}ind")}


def test_a_hanging_indent_survives(ingest_real):
    """layout.docx's list items hang their first line by 360 at every level.
    Without it they came out as plain indented lines."""

    found = indents(render_raw_xml(ingest_real("layout")[0]))

    assert {("720", "360", None), ("1440", "360", None), ("2160", "360", None)} <= found


def test_first_line_and_hanging_indents_survive(tmp_path, fixture_provider):
    from docx import Document
    from docx.shared import Twips

    document = Document()
    document.add_paragraph("first line").paragraph_format.first_line_indent = Twips(360)
    hanging = document.add_paragraph("hanging").paragraph_format
    hanging.left_indent = Twips(720)
    hanging.first_line_indent = Twips(-360)
    path = tmp_path / "indents.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")

    assert [(i.get(f"{W}left"), i.get(f"{W}hanging"), i.get(f"{W}firstLine"))
            for i in body.iter(f"{W}ind")] == [("0", None, "360"), ("720", "360", None)]


def test_start_and_end_indents_read_as_left_and_right(tmp_path, fixture_provider):
    """Newer Word and LibreOffice write w:start / w:end."""
    from docx import Document

    document = Document()
    document.add_paragraph("bidi-neutral")._p.get_or_add_pPr().append(
        fragment('<w:ind w:start="567" w:end="283" w:firstLine="200"/>')
    )
    path = tmp_path / "start_end.docx"
    document.save(path)

    ind = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f".//{W}ind")

    assert (ind.get(f"{W}left"), ind.get(f"{W}right"), ind.get(f"{W}firstLine")) == ("567", "283", "200")


def test_the_paragraph_mark_keeps_its_formatting(tmp_path, fixture_provider):
    """Word formats list numbers and bullets from the paragraph mark, and an empty
    paragraph is as tall as its mark. Without the mark both fell back to Word's own
    default font, since no styles.xml is written."""
    from docx import Document

    document = Document()
    document.styles["Normal"].font.name = "Georgia"
    document.add_paragraph("styled mark")
    empty = document.add_paragraph()
    empty._p.get_or_add_pPr().append(fragment(
        '<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/><w:b/><w:sz w:val="16"/></w:rPr>'
    ))
    path = tmp_path / "marks.docx"
    document.save(path)

    body = render_raw_xml(_ingest_docx(path, fixture_provider)).find(f"{W}body")
    marks = [p.find(f"{W}pPr/{W}rPr") for p in body.findall(f"{W}p")]

    def summary(rpr):
        return (rpr.find(f"{W}rFonts").get(f"{W}ascii"), rpr.find(f"{W}b") is not None, rpr.find(f"{W}sz").get(f"{W}val"))

    assert None not in marks
    assert summary(marks[0])[:2] == ("Georgia", False), "an unformatted mark takes the paragraph style's font"
    assert summary(marks[1]) == ("Courier New", True, "16")


def test_the_mark_comes_last_in_the_paragraph_properties(ingest_real):
    document = render_raw_xml(ingest_real("layout")[0])

    for ppr in document.iter(f"{W}pPr"):
        names = [etree.QName(child).localname for child in ppr]
        if names == ["sectPr"]:
            continue        # the paragraph that carries a section break
        assert names[-1] == "rPr", names
        assert [CT_PPR_ORDER.index(n) for n in names] == sorted(CT_PPR_ORDER.index(n) for n in names), names


# --- Task 14b: list numbering -------------------------------------------------

# CT_Lvl and CT_Numbering are xsd:sequences as well
CT_LVL_ORDER = [
    "start", "numFmt", "lvlRestart", "pStyle", "isLgl", "suff", "lvlText",
    "lvlPicBulletId", "legacy", "lvlJc", "pPr", "rPr",
]


def docx_part(docx: bytes, name: str) -> etree._Element | None:
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        return etree.fromstring(archive.read(name)) if name in archive.namelist() else None


def list_refs(document) -> Counter:
    """(numId, ilvl) of every numbered paragraph; a missing ilvl is level 0."""

    refs = Counter()
    for num_pr in document.iter(f"{W}numPr"):
        level = num_pr.find(f"{W}ilvl")
        refs[(num_pr.find(f"{W}numId").get(f"{W}val"), level.get(f"{W}val") if level is not None else "0")] += 1
    return refs


def list_levels(numbering) -> dict:
    """(numId, ilvl) -> what draws that level: format, text, alignment, indent, underline."""

    def val(node, tag):
        found = node.find(f"{W}{tag}")
        return found.get(f"{W}val") if found is not None else None

    abstracts = {a.get(f"{W}abstractNumId"): a for a in numbering.findall(f"{W}abstractNum")}
    levels = {}
    for num in numbering.findall(f"{W}num"):
        for lvl in abstracts[val(num, "abstractNumId")].findall(f"{W}lvl"):
            ind = lvl.find(f"{W}pPr/{W}ind")
            levels[(num.get(f"{W}numId"), lvl.get(f"{W}ilvl"))] = (
                val(lvl, "numFmt"), val(lvl, "lvlText"), val(lvl, "lvlJc"),
                ind.get(f"{W}left"), ind.get(f"{W}hanging"),
                val(lvl.find(f"{W}rPr"), "u") if lvl.find(f"{W}rPr") is not None else None,
            )
    return levels


def with_list(paragraph, num_id: int, level: int = 0):
    paragraph._p.get_or_add_pPr().append(
        fragment(f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num_id}"/></w:numPr>')
    )


def test_list_items_keep_their_list_and_level(ingest_real, real_template):
    """layout.docx: three bulleted lists and a numbered one, nested three deep."""

    with zipfile.ZipFile(real_template("layout")) as archive:
        source = etree.fromstring(archive.read("word/document.xml"))

    rendered = _document_xml(render_raw_docx(ingest_real("layout")[0]))

    assert list_refs(rendered) == list_refs(source)


def test_lists_are_drawn_as_the_template_draws_them(ingest_real, real_template):
    """Every level of every list: decimal / lowerLetter / lowerRoman (right-aligned)
    and the ● ○ ■ bullets, each hanging 360, the number never underlined."""

    with zipfile.ZipFile(real_template("layout")) as archive:
        source = etree.fromstring(archive.read("word/numbering.xml"))

    rendered = docx_part(render_raw_docx(ingest_real("layout")[0]), "word/numbering.xml")

    assert rendered is not None
    assert list_levels(rendered) == list_levels(source)


def test_numbering_is_written_as_a_proper_part(ingest_real):
    docx = render_raw_docx(ingest_real("layout")[0])
    numbering = docx_part(docx, "word/numbering.xml")
    rels = docx_part(docx, "word/_rels/document.xml.rels")
    types = docx_part(docx, "[Content_Types].xml")

    assert numbering is not None
    children = [etree.QName(child).localname for child in numbering]
    assert children == sorted(children), "every abstractNum comes before any num"
    for lvl in numbering.iter(f"{W}lvl"):
        names = [etree.QName(child).localname for child in lvl]
        assert [CT_LVL_ORDER.index(n) for n in names] == sorted(CT_LVL_ORDER.index(n) for n in names), names

    assert any(r.get("Type").endswith("/numbering") and r.get("Target") == "numbering.xml" for r in rels)
    assert any(o.get("PartName") == "/word/numbering.xml" for o in types)


def test_a_list_given_by_the_paragraph_style_keeps_its_bullets(tmp_path):
    """Word's way: List Bullet and List Number carry the numPr, the level carries the
    indent, and neither the paragraph nor the style sets one. Only the two lists
    used out of the nine python-docx defines are kept."""
    from docx import Document

    document = Document()
    document.add_paragraph("bullet", style="List Bullet")
    document.add_paragraph("number", style="List Number")
    path = tmp_path / "word_lists.docx"
    document.save(path)

    docx = render_raw_docx(ingest_with_assets(path, real_provider())[0])
    body = _document_xml(docx).find(f"{W}body")
    numbering = docx_part(docx, "word/numbering.xml")

    def summary(paragraph):
        num_id = paragraph.find(f"{W}pPr/{W}numPr/{W}numId")
        ind = paragraph.find(f"{W}pPr/{W}ind")
        return num_id.get(f"{W}val") if num_id is not None else None, ind.get(f"{W}left"), ind.get(f"{W}hanging")

    assert [summary(p) for p in body.findall(f"{W}p")] == [("1", "360", "360"), ("5", "360", "360")]
    assert numbering is not None
    assert sorted(n.get(f"{W}numId") for n in numbering.findall(f"{W}num")) == ["1", "5"]
    assert len(numbering.findall(f"{W}abstractNum")) == 2
    bullet_font = numbering.find(f".//{W}lvl/{W}rPr/{W}rFonts")
    assert bullet_font is not None and bullet_font.get(f"{W}ascii") == "Symbol"


def test_a_paragraphs_own_indent_beats_its_list_and_the_list_beats_the_style(tmp_path):
    """List Paragraph indents 720; list 5's level indents 360, hanging 360."""
    from docx import Document

    document = Document()
    with_list(document.add_paragraph("level over style", style="List Paragraph"), 5)
    direct = document.add_paragraph("direct over level", style="List Paragraph")
    with_list(direct, 5)
    direct._p.get_or_add_pPr().append(fragment('<w:ind w:left="1000"/>'))
    path = tmp_path / "indent_precedence.docx"
    document.save(path)

    body = render_raw_xml(ingest_with_assets(path, real_provider())[0]).find(f"{W}body")

    assert [(i.get(f"{W}left"), i.get(f"{W}hanging")) for i in body.iter(f"{W}ind")] == [
        ("360", "360"), ("1000", "360"),
    ]


def test_num_id_zero_switches_a_style_list_off(tmp_path):
    from docx import Document

    document = Document()
    with_list(document.add_paragraph("not a bullet", style="List Bullet"), 0)
    path = tmp_path / "switched_off.docx"
    document.save(path)

    docx = render_raw_docx(ingest_with_assets(path, real_provider())[0])

    assert _document_xml(docx).find(f".//{W}numPr") is None
    assert docx_part(docx, "word/numbering.xml") is None


def test_an_unknown_list_is_left_unnumbered_with_a_warning(tmp_path):
    from docx import Document

    document = Document()
    with_list(document.add_paragraph("dangling"), 77)
    path = tmp_path / "dangling.docx"
    document.save(path)

    blueprint, result = ingest_with_assets(path, real_provider())

    assert _document_xml(render_raw_docx(blueprint)).find(f".//{W}numPr") is None
    assert "numbering_missing" in codes(result.diagnostics)


def test_a_restarted_list_keeps_its_start(tmp_path):
    """Word's "Restart numbering" / "Set numbering value": a new num over the same
    definition, with a startOverride."""
    from docx import Document

    document = Document()
    document.part.numbering_part.element.append(fragment(
        '<w:num w:numId="100"><w:abstractNumId w:val="7"/>'
        '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="5"/></w:lvlOverride></w:num>'
    ))
    with_list(document.add_paragraph("five"), 100)
    path = tmp_path / "restart.docx"
    document.save(path)

    numbering = docx_part(render_raw_docx(ingest_with_assets(path, real_provider())[0]), "word/numbering.xml")

    assert numbering is not None
    num = numbering.find(f"{W}num")

    assert num.get(f"{W}numId") == "100"
    assert num.find(f"{W}abstractNumId").get(f"{W}val") == "7"
    assert num.find(f"{W}lvlOverride/{W}startOverride").get(f"{W}val") == "5"


def test_a_template_without_lists_writes_no_numbering_part():
    """The Ukrainian built-ins ship an empty numbering.xml."""

    blueprint, _ = ingest_with_assets(seed_template("DEFAULT_UKR_invoice"), real_provider())

    assert docx_part(render_raw_docx(blueprint), "word/numbering.xml") is None


# --- Task 21: embedded fonts ---------------------------------------------------

R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
FONT_RELS = "word/_rels/fontTable.xml.rels"
EMBED_ORDER = ["embedRegular", "embedBold", "embedItalic", "embedBoldItalic"]      # CT_Font


def embedded_fonts(docx: bytes) -> dict:
    """(font name, embed tag) -> (sha256 of that face's bytes, fontKey, part extension)."""
    import hashlib

    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        names = archive.namelist()
        if "word/fontTable.xml" not in names or FONT_RELS not in names:
            return {}

        targets = {r.get("Id"): r.get("Target") for r in etree.fromstring(archive.read(FONT_RELS))}
        found = {}
        for font in etree.fromstring(archive.read("word/fontTable.xml")).findall(f"{W}font"):
            for embed in font:
                tag = etree.QName(embed).localname
                if tag in EMBED_ORDER:
                    target = targets[embed.get(R_ID)]
                    found[(font.get(f"{W}name"), tag)] = (
                        hashlib.sha256(archive.read(f"word/{target}")).hexdigest(),
                        embed.get(f"{W}fontKey"),
                        target.rsplit(".", 1)[-1],
                    )
        return found


def render_with_assets(blueprint, result) -> bytes:
    """Raw-render with the ingestion bundle behind it, so fonts and images are found."""

    rendered = TemplateRenderingPipeline(BundleAssets(result.assets)).render_raw(blueprint)
    assert rendered.docx is not None
    return rendered.docx


def embed_font(path, *, name, data, key, target="fonts/font1.odttf", write_part=True):
    """Add an embedded regular face to a .docx python-docx wrote: python-docx has no
    API for it, so the package is rewritten."""

    with zipfile.ZipFile(path) as archive:
        parts = {part: archive.read(part) for part in archive.namelist()}

    table = etree.fromstring(parts["word/fontTable.xml"])
    font = etree.SubElement(table, f"{W}font")
    font.set(f"{W}name", name)
    embed = etree.SubElement(font, f"{W}embedRegular")
    embed.set(R_ID, "rId1")
    embed.set(f"{W}fontKey", key)

    parts["word/fontTable.xml"] = etree.tostring(table, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts[FONT_RELS] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font" '
        f'Target="{target}"/></Relationships>'
    ).encode()
    if write_part:
        parts[f"word/{target}"] = data

    with zipfile.ZipFile(path, "w") as archive:
        for part, content in parts.items():
            archive.writestr(part, content)


def font_asset_ids(blueprint) -> list[str]:
    document = getattr(blueprint, "document", None)
    return [
        face.asset_id
        for font in getattr(document, "fonts", ())
        for face in (font.regular, font.bold, font.italic, font.bold_italic)
        if face is not None
    ]


def test_embedded_fonts_survive_byte_for_byte(real_template):
    """formatting.docx carries IBM Plex Sans and Helvetica Neue, four faces each.
    Google Docs stores them plain, under an all-zero key."""

    path = real_template("formatting")
    blueprint, result = ingest_with_assets(path, real_provider())

    source = embedded_fonts(path.read_bytes())

    assert len(source) == 8
    assert embedded_fonts(render_with_assets(blueprint, result)) == source


def test_the_font_table_is_written_as_a_proper_part(real_template):
    blueprint, result = ingest_with_assets(real_template("formatting"), real_provider())
    docx = render_with_assets(blueprint, result)

    table = docx_part(docx, "word/fontTable.xml")
    assert table is not None
    for font in table.findall(f"{W}font"):
        assert [etree.QName(embed).localname for embed in font] == EMBED_ORDER

    assert all(r.get("Type").endswith("/font") for r in docx_part(docx, FONT_RELS)), \
        "faces are related to the font table, not to the document"
    assert any(
        r.get("Type").endswith("/fontTable") and r.get("Target") == "fontTable.xml"
        for r in docx_part(docx, "word/_rels/document.xml.rels")
    )

    types = docx_part(docx, "[Content_Types].xml")
    assert any(o.get("PartName") == "/word/fontTable.xml" for o in types)
    assert any(d.get("Extension") == "ttf" for d in types)

    # (!) CT_Settings order: displayBackgroundShape > embedTrueTypeFonts
    assert [etree.QName(child).localname for child in docx_part(docx, "word/settings.xml")] == [
        "displayBackgroundShape", "embedTrueTypeFonts",
    ]


def test_embedded_fonts_are_stored_with_the_template(session, real_template):
    """A font is an asset like a picture. If the blueprint's asset list left the
    fonts out, they would never reach the database and no render could embed them."""

    from app.assets.provider import DbAssetProvider
    from app.services.template.repository import TemplateRepository

    blueprint, result = ingest_with_assets(real_template("formatting"), real_provider())
    repo = TemplateRepository(session)
    stored = repo.get_blueprint(repo.create(blueprint, result.assets, result.source))

    ids = font_asset_ids(stored)
    provider = DbAssetProvider(session)

    assert len(ids) == 8
    assert all(provider.get(asset_id) is not None for asset_id in ids)


def test_an_obfuscated_font_keeps_its_key(tmp_path, fixture_provider):
    """Word's way: the first 32 bytes are XORed with a GUID, the part is .odttf.
    The bytes and the key go through untouched, so Word can still decode them."""
    from docx import Document

    key = "{6A0B2A4E-8C1D-4F7B-9E35-0D1C2B3A4F5E}"
    data = bytes(range(256)) * 8
    document = Document()
    document.add_paragraph("obfuscated")
    path = tmp_path / "obfuscated.docx"
    document.save(path)
    embed_font(path, name="Corporate Sans", data=data, key=key)

    blueprint, result = ingest_with_assets(path, fixture_provider)
    docx = render_with_assets(blueprint, result)

    assert embedded_fonts(docx) == embedded_fonts(path.read_bytes())
    assert embedded_fonts(docx)[("Corporate Sans", "embedRegular")][1:] == (key, "odttf")
    assert any(
        d.get("Extension") == "odttf" and d.get("ContentType").endswith("obfuscatedFont")
        for d in docx_part(docx, "[Content_Types].xml")
    )


def test_a_face_missing_from_the_file_is_skipped_with_a_warning(tmp_path, fixture_provider):
    from docx import Document

    document = Document()
    document.add_paragraph("dangling font")
    path = tmp_path / "dangling_font.docx"
    document.save(path)
    embed_font(path, name="Gone Sans", data=b"", key="{00000000-0000-0000-0000-000000000000}", write_part=False)

    blueprint, result = ingest_with_assets(path, fixture_provider)

    assert "embedded_font_missing" in codes(result.diagnostics)
    assert font_asset_ids(blueprint) == []
    assert docx_part(render_with_assets(blueprint, result), "word/fontTable.xml") is None


def test_a_font_whose_bytes_are_gone_does_not_stop_the_render(ingest_real):
    """The document still renders, in whatever font the reader has installed."""

    rendered = TemplateRenderingPipeline(NoAssets()).render_raw(ingest_real("formatting")[0])

    assert rendered.docx is not None
    assert docx_part(rendered.docx, "word/fontTable.xml") is None
    assert "missing_asset" in codes(rendered.diagnostics)


def test_a_template_without_embedded_fonts_writes_no_font_table():
    """The built-ins say embedTrueTypeFonts in their settings but carry no fonts."""

    blueprint, result = ingest_with_assets(seed_template("DEFAULT_UKR_invoice"), real_provider())
    docx = render_with_assets(blueprint, result)
    settings = docx_part(docx, "word/settings.xml")

    assert docx_part(docx, "word/fontTable.xml") is None
    assert settings is None or settings.find(f"{W}embedTrueTypeFonts") is None


# --- Task 27: page numbers keep their formatting in Word -----------------------

def field_run_parts(paragraph) -> list[str]:
    """What each run of a paragraph holds: begin / instr / separate / end / text."""

    parts = []
    for run in paragraph.findall(f"{W}r"):
        char = run.find(f"{W}fldChar")
        if char is not None:
            parts.append(char.get(f"{W}fldCharType"))
        elif run.find(f"{W}instrText") is not None:
            parts.append("instr")
        elif run.find(f"{W}t") is not None:
            parts.append("text")
    return parts


def test_a_page_number_is_written_in_the_form_word_formats(ingest_real):
    """Word recomputes a page field and formats the new number like the field code.
    A <w:fldSimple> has no code run, so Word fell back to Times New Roman 10 and
    left the old, formatted result run behind it. layout.docx's footer number is
    IBM Plex Sans, grey, italic."""

    docx = render_raw_docx(ingest_real("layout")[0])
    footer = docx_part(docx, "word/footer1.xml")

    assert footer.find(f".//{W}fldSimple") is None
    paragraph = next(p for p in footer.iter(f"{W}p") if p.find(f".//{W}instrText") is not None)
    formats = {etree.tostring(run.find(f"{W}rPr")) for run in paragraph.findall(f"{W}r")}

    assert field_run_parts(paragraph) == ["begin", "instr", "separate", "text", "end"]
    assert len(formats) == 1, "every run of the field carries the same formatting"
    rpr = paragraph.find(f"{W}r/{W}rPr")
    assert rpr.find(f"{W}i") is not None
    assert rpr.find(f"{W}color").get(f"{W}val") == "d9d9d9"


def test_our_own_page_numbers_read_back_with_their_formatting(ingest_real, tmp_path):
    """Whichever form the emitter writes, a document Plater generated must import
    again with the field, and the field's formatting, intact."""

    path = tmp_path / "rendered_layout.docx"
    path.write_bytes(render_raw_docx(ingest_real("layout")[0]))

    fields = [
        segment
        for section in _ingest_docx(path, real_provider()).sections
        for hf in (section.footers.default, section.footers.first)
        if hf is not None
        for block in hf.blocks
        if isinstance(block, ParagraphBlueprint)
        for segment in block.segments
        if type(segment).__name__ == "FieldSegment"
    ]

    assert [f.kind for f in fields] == ["PAGE", "PAGE"]
    assert (fields[0].style.italic, fields[0].style.color) == (True, "d9d9d9")
