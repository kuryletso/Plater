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


# --- manager dialogs ---------------------------------------------------------

@pytest.fixture
def manager(qt_app, session: Session):
    from app.gui.dialogs.manager_dialog import ManagerDialog
    from app.gui.dialogs.managers import organization_asset

    return ManagerDialog(organization_asset(session))


def labels(dialog) -> list[str]:
    return [dialog.list.item(i).text() for i in range(dialog.list.count())]


def asset_names() -> list[str]:
    return ["organization", "representative", "template", "measurement_unit"]


def build_asset(session: Session, name: str):
    from app.gui.dialogs import managers

    return {
        "organization": managers.organization_asset,
        "representative": managers.representative_asset,
        "template": managers.template_asset,
        "measurement_unit": managers.measurement_unit_asset,
    }[name](session)


@pytest.mark.parametrize("name", asset_names())
def test_every_manager_constructs(qt_app, session: Session, name: str):
    from app.gui.dialogs.manager_dialog import ManagerDialog

    dialog = ManagerDialog(build_asset(session, name))

    assert dialog.windowTitle()
    assert dialog.new_button.isEnabled()


@pytest.mark.parametrize("name", asset_names())
def test_manager_widgets_are_all_in_a_layout(qt_app, session: Session, name: str):
    from app.gui.dialogs.manager_dialog import ManagerDialog

    assert orphans(ManagerDialog(build_asset(session, name))) == []


@pytest.mark.parametrize("name", asset_names())
def test_manager_actions_need_a_selection(qt_app, session: Session, name: str):
    from app.gui.dialogs.manager_dialog import ManagerDialog

    dialog = ManagerDialog(build_asset(session, name))

    for button in (dialog.edit_button, dialog.delete_button):
        if button is not None:              # both are optional per asset kind
            assert not button.isEnabled()

    assert all(not button.isEnabled() for button in dialog._extra_buttons)


def test_templates_have_no_edit_but_can_be_duplicated(qt_app, session: Session):
    """A template is a versioned blueprint: 'edit' would mean importing a new
    version, so the button is absent rather than lying."""
    from app.gui.dialogs.manager_dialog import ManagerDialog

    dialog = ManagerDialog(build_asset(session, "template"))

    assert dialog.edit_button is None
    assert [button.text() for button in dialog._extra_buttons] == ["Duplicate", "Hide"]


def test_units_are_hidden_rather_than_deleted(qt_app, session: Session):
    """invoice_lines reference the unit code, so deletion is not an option."""
    from app.gui.dialogs.manager_dialog import ManagerDialog

    dialog = ManagerDialog(build_asset(session, "measurement_unit"))

    assert dialog.delete_button is None
    assert [button.text() for button in dialog._extra_buttons] == ["Hide"]


def test_dynamic_labels_are_never_blank_before_a_selection(qt_app, session: Session):
    """A callable label still has to answer for 'nothing selected'."""
    from app.gui.dialogs.manager_dialog import ManagerDialog

    for name in ("template", "measurement_unit"):
        dialog = ManagerDialog(build_asset(session, name))
        assert all(button.text() for button in dialog._extra_buttons), name


def test_the_hide_button_becomes_show_again_for_a_hidden_unit(qt_app, session: Session):
    """One button, two meanings — the label follows the selection."""
    from PySide6.QtCore import Qt

    from app.gui.dialogs.manager_dialog import ManagerDialog
    from app.services.measurement_unit.repository import MeasurementUnitRepository

    dialog = ManagerDialog(build_asset(session, "measurement_unit"))
    toggle = dialog._extra_buttons[0]

    def select(code: str) -> None:
        for position in range(dialog.list.count()):
            if dialog.list.item(position).data(Qt.ItemDataRole.UserRole) == code:
                dialog.list.setCurrentRow(position)
                return
        raise AssertionError(f"{code} not listed")

    select("hour")
    assert toggle.text() == "Hide"

    MeasurementUnitRepository(session).deactivate("hour")
    dialog.refresh()
    select("hour")

    assert toggle.text() == "Show again"


def test_the_unit_manager_lists_hidden_units(qt_app, session: Session):
    from app.gui.dialogs.manager_dialog import ManagerDialog
    from app.services.measurement_unit.repository import MeasurementUnitRepository

    MeasurementUnitRepository(session).deactivate("hour")
    dialog = ManagerDialog(build_asset(session, "measurement_unit"))

    assert any("hidden" in label for label in labels(dialog))


def test_hiding_a_unit_removes_it_from_the_line_pickers(window, session: Session):
    from app.services.measurement_unit.repository import MeasurementUnitRepository

    document = window.document_column
    document.lines.set_context(("ENG",), document._units)
    combo = document.lines._widgets[0].unit_combo
    assert combo.findData("hour") >= 0

    MeasurementUnitRepository(session).deactivate("hour")
    document.reload_units()

    assert combo.findData("hour") < 0


def test_a_row_already_using_a_hidden_unit_keeps_it(window, session: Session):
    """The assembler renders disabled units on purpose, so an existing row must
    not silently lose its unit when the unit is hidden."""
    from app.services.measurement_unit.repository import MeasurementUnitRepository

    document = window.document_column
    document.lines.set_context(("ENG",), document._units)
    widget = document.lines._widgets[0]
    widget.row.unit_code = "hour"

    MeasurementUnitRepository(session).deactivate("hour")
    document.reload_units()

    assert widget.row.unit_code == "hour"


def test_the_manager_lists_what_exists(manager, make_org):
    make_org("Acme")
    manager.refresh()

    assert any("Acme" in label for label in labels(manager))


def test_the_manager_starts_with_nothing_selected(manager, make_org):
    make_org("Acme")
    manager.refresh()

    assert not manager.edit_button.isEnabled()
    assert not manager.delete_button.isEnabled()
    assert manager.new_button.isEnabled()


def test_selecting_enables_edit_and_delete(manager, make_org):
    make_org("Acme")
    manager.refresh()

    manager.list.setCurrentRow(0)

    assert manager.edit_button.isEnabled()
    assert manager.delete_button.isEnabled()


def test_the_manager_search_filters(manager, make_org):
    make_org("Acme")
    make_org("Globex", tax_value="22222222")
    manager.refresh()

    manager.search_edit.setText("globex")

    assert len(labels(manager)) == 1
    assert "Globex" in labels(manager)[0]


def test_deleting_removes_the_row(manager, make_org, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    make_org("Acme")
    manager.refresh()
    manager.list.setCurrentRow(0)

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    manager._delete()

    assert labels(manager) == []
    assert manager.changed


def test_a_refused_delete_reports_instead_of_crashing(qt_app, session: Session,
                                                      make_org, monkeypatch):
    """Representatives refuse deletion while still attached — the banner must
    carry user_message and the list must survive."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    from app.gui.dialogs.manager_dialog import ManagedAsset, ManagerDialog
    from app.gui.text import localized
    from app.services.representative.repository import RepresentativeRepository

    organization = make_org("Acme")          # make_org attaches a representative
    repository = RepresentativeRepository(session)

    dialog = ManagerDialog(ManagedAsset(
        title="Representatives",
        list_items=lambda search: [
            (row.id, localized(row.localizations, "name"))
            for row in repository.list(search=search)
        ],
        create=lambda parent: None,
        edit=lambda parent, asset_id: False,
        delete=lambda asset_id: repository.delete(int(asset_id)),
    ))

    assert labels(dialog), "make_org should have created a representative"
    dialog.list.setCurrentRow(0)

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    dialog._delete()

    assert "detach" in dialog.banner.text().lower()
    assert labels(dialog), "the row must remain after a refused delete"
    assert not dialog.changed


def test_cancelling_the_confirmation_deletes_nothing(manager, make_org, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    make_org("Acme")
    manager.refresh()
    manager.list.setCurrentRow(0)

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    manager._delete()

    assert len(labels(manager)) == 1
    assert not manager.changed


# --- deleting something the draft points at ----------------------------------

def test_revalidate_clears_a_deleted_organization(window, make_org):
    organization = make_org("Acme")
    window.provider_column.refresh_organizations()

    widget = window.provider_column.ui.organization_list
    for position in range(widget.count()):
        if "Acme" in widget.item(position).text():
            widget.setCurrentRow(position)
            break

    assert window.draft.provider_organization_id == organization.id

    from app.services.organization.repository import OrganizationRepository

    OrganizationRepository(window._session).delete(organization.id)
    window.provider_column.revalidate()

    assert window.draft.provider_organization_id is None
    assert window.draft.provider_tax_id is None


def test_revalidate_keeps_a_surviving_selection(window, make_org):
    organization = make_org("Acme")
    make_org("Globex", tax_value="22222222")
    window.provider_column.refresh_organizations()

    widget = window.provider_column.ui.organization_list
    for position in range(widget.count()):
        if "Acme" in widget.item(position).text():
            widget.setCurrentRow(position)
            break

    window.provider_column.revalidate()

    assert window.draft.provider_organization_id == organization.id
    assert window.draft.provider_tax_id is not None


def test_revalidate_clears_a_deleted_template(window, session: Session):
    """Selection is set directly: a bare Template row has no version, and
    selecting one through the list would fail for an unrelated reason."""
    from app.db.models.core.template import Template

    template = Template(name="Throwaway", type="invoice")
    session.add(template)
    session.commit()

    window.draft.set_template(template.id, "invoice", ("ENG",))
    assert window.draft.template_id == template.id

    session.delete(template)
    session.commit()
    window.template_column.revalidate()

    assert window.draft.template_id is None


def test_revalidate_keeps_a_surviving_template(window, session: Session):
    from app.db.models.core.template import Template

    template = Template(name="Kept", type="invoice")
    session.add(template)
    session.commit()

    window.draft.set_template(template.id, "invoice", ("ENG",))
    window.template_column.revalidate()

    assert window.draft.template_id == template.id


# --- the editable next-number field ------------------------------------------

@pytest.fixture
def provider_with_sequence(window, make_org, make_sequence):
    """Sets the document type without a template: _grid_languages would
    otherwise load a blueprint, and this test needs no rendering."""

    organization = make_org("Acme")
    sequence = make_sequence(organization, prefix="INV-", counter=41, padding=5)

    window.draft.set_template(None, "invoice", ())

    column = window.provider_column
    column.refresh_organizations()
    widget = column.ui.organization_list
    for position in range(widget.count()):
        if "Acme" in widget.item(position).text():
            widget.setCurrentRow(position)
            break

    return column, sequence


def set_number(column, text: str) -> None:
    column.ui.next_number_edit.setText(text)
    column.ui.next_number_edit.editingFinished.emit()


def test_the_number_field_is_empty_without_a_sequence(window):
    field = window.provider_column.ui.next_number_edit

    assert not field.isEnabled()
    assert field.text() == ""


def test_the_number_field_shows_the_padded_next_number(provider_with_sequence):
    column, _ = provider_with_sequence

    assert column.ui.next_number_edit.isEnabled()
    assert column.ui.next_number_edit.text() == "00042"


def test_the_sequence_combo_shows_only_the_prefix(provider_with_sequence):
    """The number moved to its own field, so showing it twice would be noise."""
    column, _ = provider_with_sequence

    assert column.ui.sequence_combo.currentText() == "INV-"


def test_editing_the_number_moves_the_counter(provider_with_sequence, session: Session):
    column, sequence = provider_with_sequence

    set_number(column, "100")

    assert sequence.counter == 99
    assert column.ui.next_number_edit.text() == "00100"


def test_going_backwards_is_allowed_but_warned(provider_with_sequence):
    """Re-issuing a lost document is the reason the field exists."""
    column, sequence = provider_with_sequence

    set_number(column, "10")

    assert sequence.counter == 9
    assert column.ui.next_number_edit.property("warn") is True
    assert "already" in column.ui.next_number_edit.toolTip().lower()


def test_going_forwards_raises_no_warning(provider_with_sequence):
    column, _ = provider_with_sequence

    set_number(column, "100")

    assert column.ui.next_number_edit.property("warn") is False


@pytest.mark.parametrize("typed", ["", "0", "   "])
def test_unusable_input_restores_the_real_number(provider_with_sequence, typed: str):
    column, sequence = provider_with_sequence

    set_number(column, typed)

    assert column.ui.next_number_edit.text() == "00042"
    assert sequence.counter == 41


def test_retyping_the_same_number_changes_nothing(provider_with_sequence):
    column, sequence = provider_with_sequence

    set_number(column, "00042")

    assert sequence.counter == 41
    assert column.ui.next_number_edit.property("warn") is False


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
