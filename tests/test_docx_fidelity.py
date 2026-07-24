"""Fidelity of real-world Word documents through parse -> render.

Every case here was found by ingesting an actual Word template; python-docx writes
much cleaner OOXML than Word does, so none of these are reachable from synthetic
documents alone.
"""

from lxml import etree

from app.core.diagnostics import DiagnosticCollector
from app.document_engine.blueprint.models.segment import TextStyleBlueprint
from app.document_engine.parser.models.blocks import ParagraphNode
from app.document_engine.parser.models.inlines import RunNode
from app.document_engine.parser.parser import DocxParser
from app.document_engine.rendering.docx.run import build_run
from app.document_engine.rendering.docx.xml import qn


def parse(path) -> list:
    with DocxParser(path, diagnostics=DiagnosticCollector()) as parser:
        return parser.parse()


def runs_of(blocks) -> list[RunNode]:
    return [
        node
        for block in blocks
        if isinstance(block, ParagraphNode)
        for node in block.inlines
        if isinstance(node, RunNode)
    ]


def style(**overrides) -> TextStyleBlueprint:
    base = dict(bold=False, italic=False, underline=False,
                font_name="Calibri", font_size=20, color="000000")
    return TextStyleBlueprint(**(base | overrides))


def children_tags(run: etree._Element) -> list[str]:
    return [etree.QName(child).localname for child in run if etree.QName(child).localname != "rPr"]


# --- manual line breaks: parsing ---------------------------------------------

def test_manual_break_is_parsed_as_newline(make_break_docx):
    """Shift+Enter emits <w:br/>, which must survive as '\\n' in the run text."""
    blocks = parse(make_break_docx(["line one", "line two"]))

    assert runs_of(blocks)[0].text == "line one\nline two"


def test_consecutive_breaks_are_preserved(make_break_docx):
    blocks = parse(make_break_docx(["a", "", "b"]))

    assert runs_of(blocks)[0].text == "a\n\nb"


def test_leading_break_is_preserved(make_break_docx):
    """A blank first line — the 'empty row' case."""
    blocks = parse(make_break_docx(["", "after blank"]))

    assert runs_of(blocks)[0].text == "\nafter blank"


# --- manual line breaks: emitting --------------------------------------------

def test_emitted_run_splits_newlines_into_break_elements():
    """OOXML renders '\\n' inside <w:t> as a space; a break must be a <w:br/> element."""
    run = build_run("line one\nline two", style())

    assert children_tags(run) == ["t", "br", "t"]
    assert [t.text for t in run.findall(qn("w:t"))] == ["line one", "line two"]


def test_emitted_run_without_newline_has_a_single_text_element():
    run = build_run("no breaks here", style())

    assert children_tags(run) == ["t"]


def test_emitted_blank_line_produces_a_lone_break():
    run = build_run("\nafter blank", style())

    assert children_tags(run) == ["br", "t"]


def test_emitted_consecutive_breaks_produce_consecutive_elements():
    run = build_run("a\n\nb", style())

    assert children_tags(run) == ["t", "br", "br", "t"]


def test_emitted_trailing_break_is_kept():
    run = build_run("text\n", style())

    assert children_tags(run) == ["t", "br"]


def test_break_round_trips_from_source_to_output(make_break_docx):
    """End to end: <w:br/> in the source survives parse and comes back as <w:br/>."""
    blocks = parse(make_break_docx(["first", "second"]))
    text = runs_of(blocks)[0].text

    assert children_tags(build_run(text, style())) == ["t", "br", "t"]


# --- font size inheritance ---------------------------------------------------

def test_run_inherits_size_from_the_default_paragraph_style(make_styled_docx):
    """Word puts the body size on Normal; docDefaults often carries none at all."""
    blocks = parse(make_styled_docx([("body text", None)], normal_half_points=20))

    assert runs_of(blocks)[0].style.font_size == 20


def test_direct_run_size_overrides_the_paragraph_style(make_styled_docx):
    blocks = parse(make_styled_docx([("big heading", 30)], normal_half_points=20))

    assert runs_of(blocks)[0].style.font_size == 30


def test_mixed_sizes_resolve_independently(make_styled_docx):
    """The real template's exact shape: mostly 10pt with a couple of 15pt lines."""
    blocks = parse(make_styled_docx(
        [("heading", 30), ("body", None), ("more body", None)],
        normal_half_points=20,
    ))

    assert [r.style.font_size for r in runs_of(blocks)] == [30, 20, 20]


def test_every_body_run_inherits_the_default_size(make_styled_docx):
    blocks = parse(make_styled_docx(
        [("one", None), ("two", None)], normal_half_points=20,
    ))

    assert [r.style.font_size for r in runs_of(blocks)] == [20, 20]


def test_default_style_size_applies_inside_table_cells(tmp_path):
    """Table-cell paragraphs resolve through the same path as body paragraphs."""
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.styles["Normal"].font.size = Pt(10)
    table = document.add_table(rows=1, cols=1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    run = cell_paragraph.add_run("cell text")
    run.italic = False                     # force an rPr, as Word does

    path = tmp_path / "table_styled.docx"
    document.save(path)

    from app.document_engine.parser.models.blocks import TableNode

    cell_runs = [
        node
        for block in parse(path) if isinstance(block, TableNode)
        for row in block.rows
        for cell in row.cells
        for inner in cell.blocks if isinstance(inner, ParagraphNode)
        for node in inner.inlines if isinstance(node, RunNode)
    ]

    assert [r.style.font_size for r in cell_runs] == [20]
