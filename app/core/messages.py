"""Text, read by user but written outside GUI: errors, warnings and diagnostics.

app/core, app/services and app/document_engine neven import Qt, so they cannot 
call Qt's tr(). They mark text with QT_TRANSLATE_NOOP instead, which pyside6-lupdate 
finds by its name alone, and the GUI translates it wherever it shows it (app/gui/i18n.py).

A message is a template. Values go in {named} fields, filled from the error's or 
the diagnostic's context, so a translation can put them wherever its grammar needs them.
Whatever comes from the user's data is a value and isn't a part of a template.
"""

from __future__ import annotations

from collections.abc import Mapping

CONTEXT = "messages"

def QT_TRANSLATE_NOOP(context: str, text: str) -> str:
    """Marks `text` for translation and returns it unchanged. 
    The name is standard for pyside6-lupdate. `context` value always should be 
    passed as literal: lupdate reads the source, not the constant.
    """

    return text


def fill(template: str, values: Mapping[str, object] | None = None) -> str:
    """The template with its fields filled in. A field without a value 
    is left as written, and a template that does not parse comes back unchanged.
    """

    try:
        return template.format_map(_Values(values or {}))
    except (ValueError, IndexError, AttributeError, KeyError, TypeError):
        return template


def literal(text: str) -> str:
    """Text that is not a template, as one with no fields."""
    return text.replace("{", "{{").replace("}", "}}")


class _Values(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"