"""Tests for the blueprint stage: tokenizer, segment extraction, builder."""

import re

import pytest

from app.core.diagnostics import DiagnosticCollector
from app.document_engine.parser.parser import DocxParser
from app.document_engine.normalization.structural_normalizer import StructuralNormalizer
from app.document_engine.blueprint.template_builder import TemplateBuilder
from app.document_engine.blueprint.models.template import TemplateBlueprint, TemplateConfig
from app.document_engine.blueprint.builders.tokenizer import tokenize_placeholder, TK
from app.document_engine.blueprint.builders.segments import (
    extract_segments,
    split_placeholder_key,
)
from app.document_engine.blueprint.models.segment import (
    TextSegment,
    PlaceholderSegment,
    JoinedPlaceholderSegment,
    GroupedPlaceholderSegment,
)
from app.document_engine.blueprint.errors import PlaceholderSyntaxError


# --- tokenizer ---


def test_tokenize_simple_ident():
    tokens = tokenize_placeholder("org_name")
    assert [t.kind for t in tokens] == [TK.IDENT]
    assert tokens[0].value == "org_name"


def test_tokenize_punctuation_and_string():
    tokens = tokenize_placeholder('a, (b) sep="; "')
    kinds = [t.kind for t in tokens]
    assert TK.COMMA in kinds and TK.LPAREN in kinds and TK.RPAREN in kinds
    assert TK.EQ in kinds
    string_tokens = [t for t in tokens if t.kind is TK.STRING]
    assert string_tokens[0].value == "; "


def test_tokenize_unclosed_quote_raises():
    with pytest.raises(PlaceholderSyntaxError):
        tokenize_placeholder('"unterminated')


def test_tokenize_unexpected_char_raises():
    with pytest.raises(PlaceholderSyntaxError):
        tokenize_placeholder("a @ b")


@pytest.mark.parametrize(
    "src",
    [
        pytest.param('sep=","', id="straight-double"),
        pytest.param("sep=“,”", id="curly-matched"),
        pytest.param("sep=”,”", id="curly-both-closing"),   # what real Word emits
        pytest.param("sep=«,»", id="guillemets"),
        pytest.param("sep=','", id="straight-single"),
        pytest.param("sep=‘,’", id="curly-single"),
    ],
)
def test_tokenize_accepts_typographic_quotes(src):
    """Word autocorrects straight quotes to typographic ones; sep= must survive it."""
    tokens = tokenize_placeholder(src)
    strings = [t.value for t in tokens if t.kind is TK.STRING]

    assert strings == [","]


def test_tokenize_double_and_single_quotes_do_not_cross_close():
    """A single quote must not close a double-quoted string (or vice versa)."""
    tokens = tokenize_placeholder("""sep="it's" """)
    strings = [t.value for t in tokens if t.kind is TK.STRING]

    assert strings == ["it's"]


def test_tokenize_unclosed_typographic_quote_raises():
    with pytest.raises(PlaceholderSyntaxError):
        tokenize_placeholder("“unterminated")


# --- key splitting ---


@pytest.mark.parametrize(
    "key,expected",
    [
        ("org_name", ("org_name", None)),
        ("org_name.ENG", ("org_name", "ENG")),
    ],
)
def test_split_placeholder_key_valid(key, expected):
    assert split_placeholder_key(key) == expected


@pytest.mark.parametrize(
    "key,expected",
    [
        pytest.param("PROVIDER_TYPE", ("provider_type", None), id="upper-key"),
        pytest.param("Provider_Type", ("provider_type", None), id="mixed-key"),
        pytest.param("org_name.eng", ("org_name", "ENG"), id="lower-lang"),
        pytest.param("ORG_NAME.Ukr", ("org_name", "UKR"), id="mixed-both"),
    ],
)
def test_split_placeholder_key_is_case_insensitive(key, expected):
    """Users type keys in any case in Word; keys fold to lower, languages to upper."""
    assert split_placeholder_key(key) == expected


@pytest.mark.parametrize("key", ["a.b.c", ".ENG", "org."])
def test_split_placeholder_key_invalid(key):
    with pytest.raises(PlaceholderSyntaxError):
        split_placeholder_key(key)


# --- segment extraction ---


def test_extract_simple_placeholder_registers_key(make_text_node, make_context):
    ctx = make_context()
    segments = extract_segments(make_text_node("Hello {{ org_name }}"), ctx)

    assert isinstance(segments[0], TextSegment)
    assert segments[0].text == "Hello "
    assert isinstance(segments[1], PlaceholderSegment)
    assert segments[1].key == "org_name"
    assert segments[1].language == "ENG"              # default language
    assert "org_name" in ctx.placeholders
    assert ctx.diagnostics.warnings == []


def test_extract_unknown_key_warns_and_keeps_literal(make_text_node, make_context):
    ctx = make_context()
    segments = extract_segments(make_text_node("X {{ nope }}"), ctx)

    # raw placeholder preserved as literal text
    assert any(isinstance(s, TextSegment) and "{{ nope }}" in s.text for s in segments)
    assert "nope" not in ctx.placeholders
    warnings = ctx.diagnostics.warnings
    assert len(warnings) == 1
    assert "nope" in warnings[0].text


def test_a_placeholder_syntax_warning_has_its_own_code_and_names_the_placeholder(
        make_text_node, make_context):
    """The import dialog lists these, and the user has to find the placeholder in Word."""
    ctx = make_context()
    extract_segments(make_text_node("Total: {{ org_name, = }}"), ctx)

    (warning,) = ctx.diagnostics.warnings
    assert warning.code == "unexpected_token"
    assert warning.text == "Unexpected '=' in joined placeholder: {{ org_name, = }}."


def test_an_unknown_language_is_named_in_its_warning(make_text_node, make_context):
    ctx = make_context()
    extract_segments(make_text_node("{{ org_name.DEU }}"), ctx)

    (warning,) = ctx.diagnostics.warnings
    assert warning.code == "unknown_language"
    assert warning.text == \
        "Invalid placeholder key 'org_name.DEU': 'DEU' is not a language of this template."


def test_extract_unclosed_brace_warns_not_fatal(make_text_node, make_context):
    ctx = make_context()
    segments = extract_segments(make_text_node("Broken {{ org_name and more"), ctx)

    assert all(isinstance(s, TextSegment) for s in segments)   # nothing parsed as placeholder
    warnings = ctx.diagnostics.warnings
    assert len(warnings) == 1
    assert warnings[0].code == "unclosed_placeholder"


def test_extract_joined_placeholder(make_text_node, make_context):
    ctx = make_context()
    segments = extract_segments(make_text_node("{{ org_name, invoice_no }}"), ctx)
    joined = [s for s in segments if isinstance(s, JoinedPlaceholderSegment)]
    assert len(joined) == 1
    assert len(joined[0].items) == 2
    assert {"org_name", "invoice_no"} <= set(ctx.placeholders)


def test_extract_grouped_placeholder(make_text_node, make_context):
    ctx = make_context()
    # Grouped syntax wraps inner ( ... ) groups, joined by a separator.
    segments = extract_segments(make_text_node("{{ ((org_name) (invoice_no)) }}"), ctx)
    grouped = [s for s in segments if isinstance(s, GroupedPlaceholderSegment)]
    assert len(grouped) == 1
    assert len(grouped[0].items) == 2


# --- builder end-to-end (normalized -> draft -> blueprint) ---


def _normalized_from(path):
    diags = DiagnosticCollector()
    with DocxParser(path, diagnostics=diags) as parser:
        parsed = parser.parse()
    return tuple(StructuralNormalizer.normalize(parsed, diags))


def test_build_draft_and_finalize(make_docx, fixture_provider):
    normalized = _normalized_from(
        make_docx(paragraphs=["Invoice for {{ org_name }}", "No: {{ invoice_no }}"])
    )
    diags = DiagnosticCollector()

    draft = TemplateBuilder().build_draft(
        normalized,
        default_config=fixture_provider.default_template_config(),
        placeholder_defaults=fixture_provider.placeholder_defaults(),
        languages=fixture_provider.languages(),
        diagnostics=diags,
    )

    assert {"org_name", "invoice_no"} <= set(draft.context.placeholders)
    assert isinstance(draft.config, type(draft.config))

    blueprint = TemplateBuilder().save_draft(draft)
    assert isinstance(blueprint, TemplateBlueprint)
    assert set(blueprint.placeholders) == {"org_name", "invoice_no"}
    assert isinstance(blueprint.config, TemplateConfig)


@pytest.mark.parametrize(("placeholder", "code"), [
    ("{{ ((org_name ( }}", "unexpected_token"),             # a group inside a group
    ("{{ ((org_name)) = }}", "unexpected_token"),
    ("{{ ((org_name)), sep }}", "invalid_separator"),
    ("{{ ((org_name)), invoice_no }}", "ungrouped_key"),
    ('{{ ((org_name)), "text" }}', "ungrouped_text"),
    ("{{ org_name, ( }}", "unexpected_token"),
    ("{{ org_name, sep }}", "invalid_separator"),
    ("{{ org_name invoice_no }}", "invalid_placeholder"),
    ("{{ = }}", "invalid_placeholder"),
    ("{{ org_name.DEU }}", "unknown_language"),
    ("{{ org_name. }}", "placeholder_key_no_language"),
    ("{{ a.b.c }}", "placeholder_key_several_dots"),
    ("{{ nope }}", "unknown_placeholder"),
    ("{{ }}", "empty_placeholder"),
    ('{{ org_name, "open }}', "unclosed_quote"),
    ("{{ org_name; }}", "unexpected_character"),
])
def test_a_placeholder_syntax_error_supplies_every_field_its_message_names(
        placeholder, code, make_text_node, make_context):
    """The raise fills its own template. Nothing may rely on extract_segments adding
    the placeholder's text afterwards, or str(e) shows the field unfilled."""
    from app.document_engine.blueprint.builders.segments import (
        parse_placeholder,
        text_style_bp_from_normalized,
    )

    style = text_style_bp_from_normalized(make_text_node("x").style)
    with pytest.raises(PlaceholderSyntaxError) as caught:
        parse_placeholder(placeholder, style, make_context())

    error = caught.value
    assert error.code == code
    assert set(re.findall(r"\{(\w+)\}", error.user_message)) <= set(error.context)
