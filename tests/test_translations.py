"""Translations: tr() in the GUI, QT_TRANSLATE_NOOP for errors and diagnostics written
outside it, and a .ts that keeps up with the code.

The rest of the suite runs untranslated, so it keeps asserting the English source text.
"""

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
TRANSLATIONS_DIR = APP_DIR / "gui" / "translations"
UKRAINIAN = TRANSLATIONS_DIR / "plater_uk.ts"

FIELD = re.compile(r"\{(\w+)\}")


def qt_tool(name: str) -> str:
    """The PySide6 tools sit beside the interpreter in the virtual environment."""

    found = shutil.which(name, path=str(Path(sys.executable).parent)) or shutil.which(name)
    if found is None:
        pytest.skip(f"{name} is not installed")
    return found


def messages(ts: Path) -> list[etree._Element]:
    return list(etree.parse(str(ts)).getroot().iter("message"))


def context_of(message: etree._Element) -> str:
    return message.getparent().findtext("name") or ""


def entries(ts: Path) -> set[tuple[str, str, bool]]:
    return {
        (context_of(m), m.findtext("source") or "", m.get("numerus") == "yes")
        for m in messages(ts)
    }


def forms(message: etree._Element) -> list[str]:
    translation = message.find("translation")
    if message.get("numerus") == "yes":
        return [form.text or "" for form in translation.iter("numerusform")]
    return [translation.text or ""]


def unfinished(message: etree._Element) -> bool:
    return message.find("translation").get("type") == "unfinished"


def app_modules(*parts: str) -> list[Path]:
    """The app's own modules under app/<parts>, without the compiled Designer forms."""

    generated = APP_DIR / "gui" / "generated"
    return [
        path for path in sorted(APP_DIR.joinpath(*parts).rglob("*.py"))
        if generated not in path.parents
    ]


@pytest.fixture
def compiled(tmp_path) -> Path:
    """The committed .ts compiled into a temporary directory: the .qm is not committed."""

    subprocess.run(
        [qt_tool("pyside6-lrelease"), "-silent", str(UKRAINIAN), "-qm", str(tmp_path / "plater_uk.qm")],
        check=True,
    )
    return tmp_path


@pytest.fixture
def ukrainian(qt_app, compiled):
    from app.gui.i18n import install, uninstall

    assert install(qt_app, "UKR", compiled)
    yield
    uninstall()


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATER_SETTINGS", str(tmp_path / "plater.ini"))


# --- messages written outside the GUI ------------------------------------------

def test_a_message_takes_its_values_from_named_fields():
    from app.core.messages import fill

    assert fill("Line {line} has no {language} description.", {"line": 2, "language": "UKR"}) \
        == "Line 2 has no UKR description."


def test_a_field_without_a_value_is_left_as_written():
    from app.core.messages import fill

    assert fill("'{key}' is not a known placeholder.", {}) == "'{key}' is not a known placeholder."


def test_a_template_that_does_not_parse_comes_back_unchanged():
    from app.core.messages import fill

    assert fill("Unclosed { brace", {"brace": 1}) == "Unclosed { brace"


def test_a_value_is_never_read_as_a_template():
    """Values come from the user's template, which is full of braces."""
    from app.core.messages import fill

    assert fill("Unknown key '{key}'.", {"key": "{{ total }}"}) == "Unknown key '{{ total }}'."


def test_an_error_without_a_developer_message_is_its_user_message_filled_in():
    from app.services.errors import InvalidSelection

    error = InvalidSelection(
        user_message="A unit with the code '{code}' already exists.",
        context={"code": "pc"},
    )

    assert str(error) == "A unit with the code 'pc' already exists."
    assert error.user_text == str(error)
    assert error.user_message == "A unit with the code '{code}' already exists.", \
        "the template is kept, so the GUI can translate it"


def test_a_developer_message_becomes_a_diagnostic_with_no_fields():
    """It is not a template, so its braces must not be read as fields."""
    from app.document_engine.parser.errors import ParserFormatError

    diagnostic = ParserFormatError("Missing part: word/{name}.xml.").as_diagnostic()

    assert diagnostic.text == "Missing part: word/{name}.xml."


def test_a_diagnostic_is_its_message_filled_from_its_context(diagnostics):
    from app.core.errors import Layer

    diagnostics.warn(Layer.RENDER, "blank_description",
                     "Line {line} has no {language} description.", line=3, language="UKR")

    assert diagnostics.items[0].text == "Line 3 has no UKR description."


# --- installing a language -------------------------------------------------------

def test_ukrainian_translates_the_interface(ukrainian, session, seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog

    assert SettingsDialog(session).windowTitle() == "Налаштування"


def test_ukrainian_dates_follow_the_interface(ukrainian):
    from PySide6.QtCore import QLocale

    assert QLocale().language() == QLocale.Language.Ukrainian


def test_english_needs_no_translation_file(qt_app, tmp_path):
    from PySide6.QtCore import QCoreApplication

    from app.gui.i18n import install, uninstall

    try:
        assert install(qt_app, "ENG", tmp_path)
        assert QCoreApplication.translate("SettingsDialog", "Settings") == "Settings"
    finally:
        uninstall()


def test_a_missing_translation_leaves_the_interface_english_and_says_so(qt_app, tmp_path, caplog):
    """A developer who has not run build_ui.py yet still gets a working app."""
    from PySide6.QtCore import QCoreApplication, QLocale

    from app.gui.i18n import install, uninstall

    try:
        assert not install(qt_app, "UKR", tmp_path)
        assert QCoreApplication.translate("SettingsDialog", "Settings") == "Settings"
        assert QLocale().name() == QLocale.system().name()
    finally:
        uninstall()

    assert any("build_ui.py" in record.getMessage() for record in caplog.records)


def test_uninstalling_returns_to_english(qt_app, compiled):
    from PySide6.QtCore import QCoreApplication

    from app.gui.i18n import install, uninstall

    install(qt_app, "UKR", compiled)
    uninstall()

    assert QCoreApplication.translate("SettingsDialog", "Settings") == "Settings"


def test_every_interface_language_has_a_translation():
    from app.gui.i18n import LOCALES

    for code, locale in LOCALES.items():
        language = locale.split("_")[0]
        assert (TRANSLATIONS_DIR / f"plater_{language}.ts").exists(), code


def test_errors_are_translated_where_they_are_shown(ukrainian):
    from app.gui.i18n import error_text
    from app.services.errors import InvalidSelection

    error = InvalidSelection(
        user_message="A unit with the code '{code}' already exists.",
        context={"code": "pc"},
    )

    text = error_text(error)
    assert "pc" in text
    assert text != error.user_text


# --- the .ts -----------------------------------------------------------------------

def test_the_translation_source_is_up_to_date_with_the_code(tmp_path):
    """Run scripts/update_translations.py when this fails."""

    spec = importlib.util.spec_from_file_location("update_translations", PROJECT_ROOT / "scripts" / "update_translations.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    listing = tmp_path / "sources.lst"
    listing.write_text("\n".join(str(path) for path in script.sources()), encoding="utf-8")

    refreshed = tmp_path / UKRAINIAN.name
    shutil.copy(UKRAINIAN, refreshed)
    subprocess.run(
        [
            qt_tool("pyside6-lupdate"), f"@{listing}",
            "-ts", str(refreshed),
            "-locations", "none",
            "-no-obsolete",
            "-silent",
        ],
        check=True,
    )

    added = entries(refreshed) - entries(UKRAINIAN)
    gone = entries(UKRAINIAN) - entries(refreshed)
    assert not added and not gone, f"new in the code: {sorted(added)}; gone from it: {sorted(gone)}"


@pytest.mark.xfail(strict=True, reason="phase 4: the Ukrainian draft is complete")
def test_everything_is_translated():
    missing = [
        f"[{context_of(m)}] {m.findtext('source')}"
        for m in messages(UKRAINIAN) if unfinished(m)
    ]
    assert missing == []


def test_a_translation_keeps_the_fields_of_its_source():
    """fill() leaves a misspelled field as written, so the user would see '{lnie}'."""

    wrong = []
    for message in messages(UKRAINIAN):
        if unfinished(message):
            continue
        source = message.findtext("source") or ""
        expected = set(FIELD.findall(source))
        for form in forms(message):
            if set(FIELD.findall(form)) != expected or ("%n" in source) != ("%n" in form):
                wrong.append(f"[{context_of(message)}] {source!r} -> {form!r}")

    assert wrong == []


# --- marking -----------------------------------------------------------------------

def _marking_calls(path: Path):
    """(function, call) for every tr(), translate() and QT_TRANSLATE_NOOP() in `path`."""

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "tr":
            yield "tr", node
        elif isinstance(function, ast.Attribute) and function.attr == "translate" \
        and isinstance(function.value, ast.Name) and function.value.id == "QCoreApplication":
            yield "translate", node
        elif isinstance(function, ast.Name) and function.id == "QT_TRANSLATE_NOOP":
            yield "QT_TRANSLATE_NOOP", node


def _is_text(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def test_marked_text_is_a_literal():
    """lupdate reads the source: an f-string or a variable is silently left out,
    and stays English. Values go in afterwards, with .format() or fill()."""

    shown = APP_DIR / "gui" / "i18n.py"     # translates what was marked elsewhere

    wrong = []
    for path in app_modules():
        for function, call in _marking_calls(path):
            arguments = call.args
            text = arguments[0] if function == "tr" else (arguments[1] if len(arguments) > 1 else None)
            context = None if function == "tr" else (arguments[0] if arguments else None)
            if path == shown and isinstance(text, ast.Name):
                continue
            if not _is_text(text) or (function != "tr" and not _is_text(context)):
                wrong.append(f"{path.relative_to(PROJECT_ROOT)}:{call.lineno} {function}")

    assert wrong == []


def test_messages_outside_the_gui_use_the_context_the_gui_translates_with():
    from app.core.messages import CONTEXT

    wrong = [
        f"{path.relative_to(PROJECT_ROOT)}:{call.lineno}"
        for parts in (("core",), ("services",), ("document_engine",))
        for path in app_modules(*parts)
        for function, call in _marking_calls(path)
        if function == "QT_TRANSLATE_NOOP" and call.args[0].value != CONTEXT
    ]
    assert wrong == []


def _marked(node: ast.AST | None) -> bool:
    return (
        node is None
        or (isinstance(node, ast.Constant) and node.value is None)
        or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "QT_TRANSLATE_NOOP")
        or (isinstance(node, ast.Attribute) and node.attr in {"user_message", "message"})
    )


def test_every_message_for_the_user_is_marked_for_translation():
    """user_message=..., and the message of every warning and validation error. A
    placeholder syntax error always reaches the user, as an import warning."""

    wrong = []
    for parts in (("core",), ("services",), ("document_engine",)):
        for path in app_modules(*parts):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                candidates = [k.value for k in node.keywords if k.arg == "user_message"]
                function = node.func
                if isinstance(function, ast.Name) and function.id == "PlaceholderSyntaxError" and not candidates:
                    wrong.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} no user_message")
                if isinstance(function, ast.Attribute) and function.attr == "warn" and len(node.args) >= 3:
                    candidates.append(node.args[2])
                if isinstance(function, ast.Name) and function.id == "error" and len(node.args) >= 2:
                    candidates.append(node.args[1])         # validate_context's helper
                wrong += [
                    f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}"
                    for candidate in candidates if not _marked(candidate)
                ]

    assert wrong == []


def test_diagnostics_are_translated_where_they_are_shown(ukrainian):
    from app.core.diagnostics import Diagnostic
    from app.core.errors import Layer, Severity
    from app.gui.i18n import diagnostic_text, severity_label

    item = Diagnostic(
        Layer.RENDER, Severity.WARNING, "blank_description",
        "Line {line} has no {language} description; it will print blank.",
        {"line": 2, "language": "UKR"},
    )

    assert diagnostic_text(item) == "Рядок 2 не має опису мовою UKR; у документі опис буде порожнім."
    assert severity_label(Severity.WARNING) == "Попередження"


def test_a_message_from_the_users_template_is_still_filled_in_ukrainian(ukrainian):
    """The value comes from the template; the translation only moves it."""
    from app.document_engine.blueprint.errors import PlaceholderSyntaxError
    from app.gui.i18n import error_text

    error = PlaceholderSyntaxError(
        code="unknown_placeholder",
        user_message="Unknown placeholder key '{key}'.",
        context={"key": "clinet_name"},
    )

    assert error_text(error) == "Невідомий ключ заповнювача «clinet_name»."


def _template(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
    and node.func.id == "QT_TRANSLATE_NOOP" and len(node.args) == 2 and _is_text(node.args[1]):
        return node.args[1].value
    return None


def test_every_field_of_a_message_has_a_value_where_it_is_written():
    """fill() leaves a field without a value as written, so '{type}' against
    width_type=type shows the user a literal '{type}' and fails nothing else."""

    wrong = []
    for parts in (("core",), ("services",), ("document_engine",)):
        for path in app_modules(*parts):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                checks = []

                keywords = {k.arg: k.value for k in node.keywords if k.arg}
                template = _template(keywords.get("user_message"))
                context = keywords.get("context")
                if template is not None and (context is None or isinstance(context, ast.Dict)):
                    names = {k.value for k in context.keys if _is_text(k)} if context is not None else set()
                    checks.append((template, names))

                function = node.func
                if isinstance(function, ast.Attribute) and function.attr == "warn":
                    position = 2
                elif isinstance(function, ast.Name) and function.id == "error":
                    position = 1        # validate_context's helper
                else:
                    position = None
                if position is not None and len(node.args) > position:
                    template = _template(node.args[position])
                    if template is not None:
                        checks.append((template, set(keywords)))

                for template, names in checks:
                    if missing := set(FIELD.findall(template)) - names:
                        wrong.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {sorted(missing)}")

    assert wrong == []


def test_the_gui_shows_errors_and_diagnostics_only_through_i18n():
    """Read directly, a message is the English template with its fields unfilled."""

    shown = APP_DIR / "gui" / "i18n.py"
    wrong = [
        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} .{node.attr}"
        for path in app_modules("gui") if path != shown
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Attribute) and node.attr in {"user_message", "user_text", "message"}
    ]
    assert wrong == []
