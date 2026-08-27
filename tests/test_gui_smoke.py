"""The GUI is otherwise untested, so a bad import path, a connect(self.reject())
typo, or a widget added to no layout ships silently and breaks the whole app.

These tests only construct things. They are cheap insurance against the class of
mistake that cannot survive a single launch, not a substitute for driving the UI.
"""

import importlib
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from sqlalchemy.orm import Session

GUI_ROOT = Path(__file__).resolve().parent.parent / "app" / "gui"


def gui_modules() -> list[str]:
    return [
        ".".join(path.relative_to(GUI_ROOT.parent.parent).with_suffix("").parts)
        for path in sorted(GUI_ROOT.rglob("*.py"))
        if path.name != "__init__.py"
    ]


def orphans(widget: QWidget) -> list[str]:
    """Widgets built in __init__ but never added to a layout keep no parent —
    they simply never appear, with nothing to notice at runtime."""

    return [
        name
        for name, value in vars(widget).items()
        if isinstance(value, QWidget) and value.parentWidget() is None
    ]


@pytest.fixture
def window(qt_app, session: Session, monkeypatch):
    """MainWindow builds its own session; point it at the test database."""

    from app.gui import main_window as module

    monkeypatch.setattr(module, "SessionLocal", lambda: session)
    return module.MainWindow()


# --- imports -----------------------------------------------------------------

@pytest.mark.parametrize("name", gui_modules())
def test_every_gui_module_imports(name: str):
    importlib.import_module(name)


def test_the_module_list_is_not_accidentally_empty():
    """A broken glob would make the parametrized test vacuously pass."""

    assert len(gui_modules()) > 5


# --- the window --------------------------------------------------------------

def test_main_window_constructs(window):
    assert window.template_column is not None
    assert window.provider_column is not None
    assert window.client_column is not None
    assert window.document_column is not None


def test_the_window_has_all_four_accordion_columns(window):
    from app.gui.draft_state import COLUMNS

    assert set(window._columns) == set(COLUMNS)


def test_the_window_starts_with_generation_blocked(window):
    assert not window.generate_button.isEnabled()
    assert window.draft.missing_by_column()


def test_the_preview_starts_with_a_notice(window):
    assert "preview" in window.preview.status_label.text().lower()


@pytest.mark.parametrize(
    "attribute",
    ["preview", "template_column", "provider_column", "client_column", "document_column"],
)
def test_window_widgets_are_all_in_a_layout(window, attribute):
    widget = getattr(window, attribute)

    assert widget.parentWidget() is not None
    assert orphans(widget) == []


# --- dialogs -----------------------------------------------------------------

@pytest.fixture
def organization(session: Session, make_org):
    return make_org("Acme")


def build_dialogs(session: Session, organization_id: int) -> dict[str, QWidget]:
    from app.gui.dialogs.bank_account import BankAccountDialog
    from app.gui.dialogs.measurement_unit import MeasurementUnitDialog
    from app.gui.dialogs.organization import OrganizationDialog
    from app.gui.dialogs.representative import RepresentativeDialog
    from app.gui.dialogs.sequence import SequenceDialog
    from app.gui.dialogs.tax_id import TaxIdDialog
    from app.gui.dialogs.template_import import TemplateImportDialog

    return {
        "organization": OrganizationDialog(session),
        "tax_id": TaxIdDialog(session, organization_id),
        "sequence": SequenceDialog(session, organization_id, "invoice"),
        "representative": RepresentativeDialog(session, organization_id),
        "bank_account": BankAccountDialog(session, organization_id),
        "measurement_unit": MeasurementUnitDialog(session),
        "template_import": TemplateImportDialog(session),
    }


def dialog_names() -> list[str]:
    return [
        "organization", "tax_id", "sequence", "representative",
        "bank_account", "measurement_unit", "template_import",
    ]


@pytest.mark.parametrize("name", dialog_names())
def test_every_dialog_constructs(qt_app, session: Session, organization, name: str):
    dialog = build_dialogs(session, organization.id)[name]

    assert dialog.windowTitle()


@pytest.mark.parametrize("name", dialog_names())
def test_dialog_widgets_are_all_in_a_layout(qt_app, session: Session, organization,
                                             name: str):
    dialog = build_dialogs(session, organization.id)[name]

    assert orphans(dialog) == []


@pytest.mark.parametrize("name", dialog_names())
def test_every_dialog_can_be_rejected(qt_app, session: Session, organization, name: str):
    """Cancel must be wired to the method, not to its return value."""

    dialog = build_dialogs(session, organization.id)[name]
    dialog.reject()

    assert dialog.result() == dialog.DialogCode.Rejected


# --- defaults that are easy to forget ----------------------------------------

def test_template_import_preselects_its_defaults(qt_app, session: Session, seeded_inputs):
    from app.gui.dialogs.template_import import TemplateImportDialog

    dialog = TemplateImportDialog(session)

    assert dialog.type_combo.code() == "invoice"
    assert dialog.primary_combo.code() == "ENG"
    assert dialog.secondary_combo.code() == ""      # imports are single-language


def test_template_import_accepts_drops(qt_app, session: Session):
    from app.gui.dialogs.template_import import TemplateImportDialog

    assert TemplateImportDialog(session).acceptDrops()


def test_localized_fields_open_the_configured_languages(qt_app, session: Session,
                                                        seeded_inputs):
    from app.gui.dialogs.organization import OrganizationDialog

    dialog = OrganizationDialog(session)

    assert dialog.localizations.tabs.count() == 2


# --- reference pickers -------------------------------------------------------

def test_reference_pickers_resolve_any_language(qt_app, session: Session):
    """The UI language must never limit what a user can type."""

    from app.gui.dialogs.widgets import country_items, searchable_combo

    combo = searchable_combo(country_items(session))
    for typed in ("Ukraine", "Україна", "UKR"):
        combo.lineEdit().setText(typed)
        assert combo.code() == "UKR", typed


def test_reference_pickers_offer_aliases_as_completions(qt_app, session: Session):
    """Resolution alone is not enough: an empty popup looks broken."""

    from app.gui.dialogs.widgets import country_items, searchable_combo

    combo = searchable_combo(country_items(session))     # must outlive its completer
    completer = combo.completer()

    completer.setCompletionPrefix("Україн")
    assert completer.completionCount() >= 1

    completer.setCompletionPrefix("Ukrai")
    assert completer.completionCount() >= 1
