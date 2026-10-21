"""The issue date: one pattern per template, month names in each document language."""

from datetime import date

import pytest

MAY_4 = date(2026, 5, 4)


@pytest.mark.parametrize(("pattern", "english", "ukrainian"), [
    ("y-MM-dd", "2026-05-04", "2026-05-04"),
    ("dd.MM.y", "04.05.2026", "04.05.2026"),
    ("MM/dd/y", "05/04/2026", "05/04/2026"),
    ("d MMMM y", "4 May 2026", "4 травня 2026"),
    ("MMMM d, y", "May 4, 2026", "травня 4, 2026"),       # why it is offered for English only
])
def test_each_format_in_each_language(pattern, english, ukrainian):
    from app.services.dates import format_document_date

    assert format_document_date(MAY_4, pattern, "en") == english
    assert format_document_date(MAY_4, pattern, "uk") == ukrainian


def test_a_language_babel_does_not_know_gets_english_months():
    from app.services.dates import format_document_date

    assert format_document_date(MAY_4, "d MMMM y", "xx") == "4 May 2026"
    assert format_document_date(MAY_4, "d MMMM y", None) == "4 May 2026"


def test_only_the_offered_formats_are_accepted():
    from app.services.dates import DATE_FORMATS, check_date_format
    from app.services.errors import InvalidSelection

    assert len(DATE_FORMATS) == 5
    with pytest.raises(InvalidSelection):
        check_date_format("%d.%m.%Y")


def test_a_template_from_before_the_date_format_stays_iso():
    """Stored configs have no date_format; they keep printing what they printed."""
    from app.document_engine.blueprint.models.template import TemplateConfig
    from app.services.dates import DEFAULT_DATE_FORMAT

    config = TemplateConfig.model_validate({
        "primary_language": "ENG", "secondary_language": None, "type": "invoice",
        "name": "Old", "description": "", "append_currency": True,
    })

    assert config.date_format == DEFAULT_DATE_FORMAT == "y-MM-dd"
