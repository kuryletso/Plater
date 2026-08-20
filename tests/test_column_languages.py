"""column_languages(): which languages a template actually renders a table column in.

This is what decides how many description columns the invoice-lines grid shows —
a template whose config declares a secondary language may still never place
invl_desc.UKR in its table, and warning about an empty cell nobody renders
would be noise.
"""

import pytest

from app.document_engine.enums.enums import PlaceholderType
from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
from app.document_engine.rendering.validate import column_languages

from tests.conftest import FixtureInputProvider


def provider(languages: set[str] | None = None, *, primary: str = "ENG") -> FixtureInputProvider:
    from app.document_engine.blueprint.models.template import TemplateConfig

    return FixtureInputProvider(
        languages=languages,
        placeholders={
            "invl_desc": {"active": True, "required": False, "type": PlaceholderType.COLUMN},
            "invl_qnty": {"active": True, "required": False, "type": PlaceholderType.COLUMN},
            "org_name": {"active": True, "required": True, "type": PlaceholderType.SCALAR},
        },
        config=TemplateConfig(
            primary_language=primary,
            secondary_language="UKR" if primary == "ENG" else "ENG",
            type="invoice",
            name="t",
            description="",
            append_currency=False,
        ),
    )


def ingest(path, input_provider=None):
    pipeline = TemplateIngestionPipeline(input_provider or provider())
    return pipeline.finalize(pipeline.ingest(path).draft)


def test_an_unsuffixed_column_resolves_to_the_default_language(make_docx):
    blueprint = ingest(make_docx(table=[["{{ invl_desc }}"]]))

    assert column_languages(blueprint, "invl_desc") == {"ENG"}


def test_both_languages_are_reported_for_a_bilingual_column(make_docx):
    blueprint = ingest(make_docx(table=[["{{ invl_desc.ENG }}", "{{ invl_desc.UKR }}"]]))

    assert column_languages(blueprint, "invl_desc") == {"ENG", "UKR"}


def test_a_declared_but_unused_second_language_is_not_reported(make_docx):
    """The whole point: the config says bilingual, the table says otherwise."""
    blueprint = ingest(make_docx(table=[["{{ invl_desc.ENG }}", "{{ invl_qnty }}"]]))

    assert column_languages(blueprint, "invl_desc") == {"ENG"}


def test_an_absent_column_reports_nothing(make_docx):
    """The grid falls back to the config's primary language in this case."""
    blueprint = ingest(make_docx(table=[["{{ invl_qnty }}"]]))

    assert column_languages(blueprint, "invl_desc") == set()


def test_columns_are_reported_per_key(make_docx):
    blueprint = ingest(make_docx(table=[["{{ invl_desc.UKR }}", "{{ invl_qnty.ENG }}"]]))

    assert column_languages(blueprint, "invl_desc") == {"UKR"}
    assert column_languages(blueprint, "invl_qnty") == {"ENG"}


def test_a_scalar_of_the_same_name_outside_a_table_is_not_a_column(make_docx):
    """Only table cells count — a paragraph mention must not widen the grid."""
    blueprint = ingest(make_docx(paragraphs=["{{ invl_desc.UKR }}"],
                                 table=[["{{ invl_desc.ENG }}"]]))

    assert column_languages(blueprint, "invl_desc") == {"ENG"}
