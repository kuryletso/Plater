"""End-to-end tests for the template ingestion pipeline."""

import zipfile
from collections.abc import Mapping

import pytest

from app.core.errors import Layer
from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
from app.document_engine.orchestration.results import IngestionResult
from app.document_engine.orchestration.errors import IngestionError
from app.document_engine.blueprint.models.template import TemplateBlueprint, TemplateConfig
from app.document_engine.parser.errors import ParserError

from tests.conftest import FixtureInputProvider


def test_ingest_returns_draft_and_registers_placeholders(make_docx, fixture_provider):
    path = make_docx(
        paragraphs=["Invoice for {{ org_name }}", "Number {{ invoice_no }}"],
        table=[["Item", "Total"]],
    )
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert isinstance(result, IngestionResult)
    assert len(result.draft.sections) == 1
    assert {"org_name", "invoice_no"} <= set(result.draft.context.placeholders)
    assert result.diagnostics.warnings == []


def test_ingest_surfaces_warning_for_unknown_placeholder(make_docx, fixture_provider):
    path = make_docx(paragraphs=["Hello {{ unknown_key }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert len(result.diagnostics.warnings) == 1
    assert result.diagnostics.warnings[0].layer is Layer.BLUEPRINT
    assert "unknown_key" not in result.draft.context.placeholders


def test_finalize_produces_blueprint(make_docx, fixture_provider):
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)
    blueprint = pipeline.finalize(result.draft)

    assert isinstance(blueprint, TemplateBlueprint)
    assert "org_name" in blueprint.placeholders


def test_ingest_wraps_stage_failure_in_ingestion_error(tmp_path, fixture_provider):
    bogus = tmp_path / "bogus.docx"
    with zipfile.ZipFile(bogus, "w") as zf:
        zf.writestr("not-a-docx.txt", "hello")

    pipeline = TemplateIngestionPipeline(fixture_provider)

    with pytest.raises(IngestionError) as excinfo:
        pipeline.ingest(bogus)

    # original parser failure is attached as the cause, attributed to orchestration
    assert excinfo.value.layer is Layer.ORCHESTRATION
    assert isinstance(excinfo.value.__cause__, ParserError)


def test_fixture_provider_satisfies_input_protocol(fixture_provider):
    assert isinstance(fixture_provider.languages(), set)
    assert isinstance(fixture_provider.placeholder_defaults(), dict)
    assert fixture_provider.default_template_config().primary_language == "ENG"


def test_provider_derives_languages_from_its_config(fixture_provider):
    """languages() is the template's renderable set, not every known language."""
    config = fixture_provider.default_template_config()

    assert fixture_provider.languages() == {"ENG", "UKR"}
    assert fixture_provider.languages() == {config.primary_language, config.secondary_language}


def test_provider_drops_absent_secondary_language():
    provider = FixtureInputProvider(config=TemplateConfig(
        primary_language="ENG",
        secondary_language=None,
        type="invoice",
        name="seed",
        description="",
        append_currency=False,
    ))

    assert provider.languages() == {"ENG"}


def test_provider_honours_an_explicit_language_override():
    provider = FixtureInputProvider(languages={"ENG", "UKR", "DEU"})

    assert provider.languages() == {"ENG", "UKR", "DEU"}


def test_language_suffix_outside_the_provider_set_is_rejected(make_docx, fixture_provider):
    """A `.DEU` suffix can never be filled, so ingestion must warn rather than accept it."""
    path = make_docx(paragraphs=["Hello {{ org_name.DEU }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert len(result.diagnostics.warnings) == 1
    assert result.diagnostics.warnings[0].layer is Layer.BLUEPRINT


def test_language_suffix_inside_the_provider_set_is_accepted(make_docx, fixture_provider):
    path = make_docx(paragraphs=["Hello {{ org_name.UKR }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert result.diagnostics.warnings == []
    assert "org_name" in result.draft.context.placeholders


@pytest.mark.parametrize(
    "runs",
    [
        pytest.param([("Hello {{ ", False), ("org_name }}", True)], id="split-after-braces"),
        pytest.param([("Hello {{ org_name", False), (" }}", True)], id="split-before-braces"),
        pytest.param([("Hello {{ org_", False), ("name }}", True)], id="split-mid-key"),
        pytest.param(
            [("{{ or", False), ("g_na", True), ("me }}", False)], id="split-three-ways"
        ),
    ],
)
def test_placeholder_survives_a_style_change_mid_placeholder(runs, make_runs, fixture_provider):
    """Word splits runs freely; a placeholder broken by formatting must still resolve."""
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(make_runs(runs))

    assert "org_name" in result.draft.context.placeholders
    assert result.diagnostics.warnings == []


def test_a_non_docx_file_is_wrapped_in_an_ingestion_error(tmp_path, fixture_provider):
    """The GUI file picker will hand us arbitrary files; the pipeline must not leak raw errors."""
    path = tmp_path / "holiday_photo.docx"
    path.write_bytes(b"\xff\xd8\xff\xe0 JPEG data")

    pipeline = TemplateIngestionPipeline(fixture_provider)

    with pytest.raises(IngestionError) as excinfo:
        pipeline.ingest(path)

    assert excinfo.value.layer is Layer.ORCHESTRATION
    assert isinstance(excinfo.value.__cause__, ParserError)


def test_uppercase_placeholder_key_resolves(make_docx, fixture_provider):
    """Regression: a real template wrote {{ ORG_NAME }} and it was silently rejected."""
    path = make_docx(paragraphs=["Provider {{ ORG_NAME }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert "org_name" in result.draft.context.placeholders
    assert result.diagnostics.warnings == []


def test_joined_placeholder_with_word_smart_quotes_resolves(make_docx, fixture_provider):
    """Regression: Word autocorrected sep="," to typographic quotes, breaking the join."""
    path = make_docx(paragraphs=["{{ org_name, invoice_no, sep=”,” }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert {"org_name", "invoice_no"} <= set(result.draft.context.placeholders)
    assert result.diagnostics.warnings == []


def test_ingest_returns_an_asset_bundle(make_docx, fixture_provider):
    """Image-free templates still carry a (empty) bundle for the repository to persist."""
    path = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    pipeline = TemplateIngestionPipeline(fixture_provider)

    result = pipeline.ingest(path)

    assert isinstance(result.assets, Mapping)
    assert result.assets == {}
