"""Tests for the structural normalizer (normalize stage)."""

import pytest

from app.core.diagnostics import DiagnosticCollector
from app.document_engine.parser.parser import DocxParser
from app.document_engine.parser.models.blocks import SectionBreakNode
from app.document_engine.normalization.structural_normalizer import StructuralNormalizer
from app.document_engine.normalization.models.blocks import (
    NormalizedParagraph,
    NormalizedTable,
)
from app.document_engine.normalization.models.inlines import NormalizedTextNode
from app.document_engine.normalization.errors import NormalizationFormatError


def _parse(path) -> list:
    with DocxParser(path, diagnostics=DiagnosticCollector()) as parser:
        return parser.parse()


def test_normalize_groups_blocks_into_section(make_docx):
    parsed = _parse(make_docx(paragraphs=["one", "two"], table=[["A", "B"]]))

    sections = StructuralNormalizer.normalize(parsed, DiagnosticCollector())

    assert len(sections) == 1
    block_kinds = [type(b).__name__ for b in sections[0].blocks]
    assert block_kinds == ["NormalizedParagraph", "NormalizedParagraph", "NormalizedTable"]
    assert isinstance(sections[0].blocks[0], NormalizedParagraph)
    assert isinstance(sections[0].blocks[-1], NormalizedTable)


def test_normalize_empty_list_raises():
    with pytest.raises(NormalizationFormatError):
        StructuralNormalizer.normalize([], DiagnosticCollector())


def test_normalize_invalid_block_type_raises():
    with pytest.raises(NormalizationFormatError):
        StructuralNormalizer.normalize([object()], DiagnosticCollector())


def test_normalize_without_trailing_section_break_raises(make_docx):
    parsed = _parse(make_docx(paragraphs=["dangling"]))
    # Drop the trailing section break so blocks have no section to close into.
    assert isinstance(parsed[-1], SectionBreakNode)
    truncated = parsed[:-1]

    with pytest.raises(NormalizationFormatError):
        StructuralNormalizer.normalize(truncated, DiagnosticCollector())


# --- run merging -------------------------------------------------------------
#
# A NormalizedTextNode boundary is where the blueprint tokenizes placeholders, so a
# placeholder must never be split across two nodes — otherwise its value is silently
# dropped from the rendered document.

def text_nodes(path) -> list:
    sections = StructuralNormalizer.normalize(_parse(path), DiagnosticCollector())
    paragraph = sections[0].blocks[0]
    return [n for n in paragraph.inlines if isinstance(n, NormalizedTextNode)]


def test_adjacent_runs_of_equal_style_merge(make_runs):
    nodes = text_nodes(make_runs([("Hello ", False), ("world", False)]))

    assert [n.text for n in nodes] == ["Hello world"]


def test_runs_of_differing_style_stay_separate(make_runs):
    nodes = text_nodes(make_runs([("Hello ", False), ("world", True)]))

    assert [n.text for n in nodes] == ["Hello ", "world"]


def test_placeholder_split_by_a_style_change_is_kept_whole(make_runs):
    """The regression: a style boundary inside '{{ ... }}' must not split the node."""
    nodes = text_nodes(make_runs([("Hello {{ org_", False), ("name }}", True)]))

    assert [n.text for n in nodes] == ["Hello {{ org_name }}"]


def test_split_placeholder_takes_the_style_of_its_opening_run(make_runs):
    nodes = text_nodes(make_runs([("{{ org_", False), ("name }}", True)]))

    assert nodes[0].style.bold is False


def test_text_after_a_split_placeholder_keeps_its_own_style(make_runs):
    """Absorbing stops at '}}' so the tail is not swallowed into the opening style."""
    nodes = text_nodes(make_runs([("Hello {{ org_", False), ("name }} WORLD", True)]))

    assert [n.text for n in nodes] == ["Hello {{ org_name }}", " WORLD"]
    assert nodes[0].style.bold is False
    assert nodes[1].style.bold is True


def test_placeholder_split_across_three_styled_runs(make_runs):
    nodes = text_nodes(make_runs([("{{ or", False), ("g_na", True), ("me }}", False)]))

    assert [n.text for n in nodes] == ["{{ org_name }}"]


def test_consecutive_placeholders_with_differing_styles_stay_separate(make_runs):
    """Merging is scoped to an open placeholder, not to everything that follows one."""
    nodes = text_nodes(make_runs([("{{ a }} ", False), ("{{ b }}", True)]))

    assert [n.text for n in nodes] == ["{{ a }} ", "{{ b }}"]
