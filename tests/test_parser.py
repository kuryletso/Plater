"""Tests for the DOCX parser (parse stage)."""

import zipfile

import pytest

from app.core.diagnostics import DiagnosticCollector
from app.document_engine.parser.parser import DocxParser
from app.document_engine.parser.models.blocks import (
    ParagraphNode,
    TableNode,
    SectionBreakNode,
)
from app.document_engine.parser.errors import ParserFormatError
from app.document_engine.parser.relationships import RelationshipResolver
from app.document_engine.parser.errors import ParserSecurityError


def test_parse_paragraphs_and_table(make_docx):
    path = make_docx(
        paragraphs=["First paragraph", "Second paragraph"],
        table=[["A", "B"]],
    )
    with DocxParser(path, diagnostics=DiagnosticCollector()) as parser:
        blocks = parser.parse()

    kinds = [type(b).__name__ for b in blocks]
    # python-docx always emits a trailing body sectPr -> one SectionBreakNode
    assert kinds == ["ParagraphNode", "ParagraphNode", "TableNode", "SectionBreakNode"]
    assert isinstance(blocks[0], ParagraphNode)
    assert isinstance(blocks[2], TableNode)
    assert isinstance(blocks[-1], SectionBreakNode)


def test_parser_is_context_manager_and_closes(make_docx):
    path = make_docx(paragraphs=["x"])
    parser = DocxParser(path, diagnostics=DiagnosticCollector())
    with parser as p:
        p.parse()
    # archive's underlying zip is closed on __exit__
    assert parser.archive.zip.fp is None


def test_missing_document_part_raises_format_error(tmp_path):
    bogus = tmp_path / "bogus.docx"
    with zipfile.ZipFile(bogus, "w") as zf:
        zf.writestr("not-a-docx.txt", "hello")

    with pytest.raises(ParserFormatError):
        DocxParser(bogus, diagnostics=DiagnosticCollector())


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"just some text", id="plain-text"),
        pytest.param(b"", id="empty-file"),
        pytest.param(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", id="pdf-renamed"),
        pytest.param(b"PK\x03\x04 truncated", id="truncated-zip"),
    ],
)
def test_a_file_that_is_not_a_zip_raises_format_error(tmp_path, content):
    """Users pick the wrong file all the time; that must be a diagnostic, not a crash.

    Regression: BadZipFile escaped the parser, so it was never wrapped into an
    IngestionError and reached the caller raw.
    """
    path = tmp_path / "not_really.docx"
    path.write_bytes(content)

    with pytest.raises(ParserFormatError):
        DocxParser(path, diagnostics=DiagnosticCollector())


# --- relationship target normalization (regression for the '..' fix) ---


class _FakeRelsRoot:
    """Minimal stand-in; resolver only calls findall()."""

    def findall(self, *_args, **_kwargs):
        return []


@pytest.mark.parametrize(
    "target,expected",
    [
        ("media/image1.png", "word/media/image1.png"),
        ("../customXml/item1.xml", "customXml/item1.xml"),
        ("./styles.xml", "word/styles.xml"),
    ],
)
def test_relationship_normalizes_legitimate_targets(target, expected):
    resolver = RelationshipResolver(_FakeRelsRoot())
    assert resolver._normalize_target(target) == expected


@pytest.mark.parametrize("target", ["/etc/passwd", "../../../secret"])
def test_relationship_rejects_escaping_targets(target):
    resolver = RelationshipResolver(_FakeRelsRoot())
    with pytest.raises(ParserSecurityError):
        resolver._normalize_target(target)
