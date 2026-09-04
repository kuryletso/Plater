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


def test_templates_offer_edit_versions_duplicate_and_hide(qt_app, session: Session):
    """Edit covers metadata only — content changes are a new version."""
    from app.gui.dialogs.manager_dialog import ManagerDialog

    dialog = ManagerDialog(build_asset(session, "template"))

    assert dialog.edit_button is not None
    assert [button.text() for button in dialog._extra_buttons] == [
        "Versions...", "Duplicate", "Hide",
    ]


# --- template versions -------------------------------------------------------

def versions_dialog(session: Session, template_id: int):
    from app.gui.dialogs.manager_dialog import ManagerDialog
    from app.gui.dialogs.managers import template_version_asset

    return ManagerDialog(template_version_asset(session, template_id))


def test_the_versions_list_marks_the_current_one(qt_app, session: Session,
                                                 stored_template: int):
    dialog = versions_dialog(session, stored_template)

    assert labels(dialog) == [
        label for label in labels(dialog) if "Version 1" in label
    ]
    assert "current" in labels(dialog)[0]


def test_versions_are_append_only_so_there_is_no_delete(qt_app, session: Session,
                                                        stored_template: int):
    dialog = versions_dialog(session, stored_template)

    assert dialog.delete_button is None
    assert dialog.edit_button is None
    assert [button.text() for button in dialog._extra_buttons] == ["Restore"]


def test_the_versions_list_hides_its_search_box(qt_app, session: Session,
                                                stored_template: int):
    """A handful of versions needs no filtering, and a dead box reads as broken."""
    dialog = versions_dialog(session, stored_template)

    assert not dialog.search_edit.isVisibleTo(dialog)


def test_restoring_appends_rather_than_rewinds(qt_app, session: Session,
                                               stored_template: int, make_docx,
                                               fixture_provider):
    """History stays append-only, so 'latest is current' keeps meaning what it says."""
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
    from app.services.template.repository import TemplateRepository

    repository = TemplateRepository(session)

    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(make_docx(paragraphs=["Revised {{ org_name }}"],
                                       name="v2.docx"))
    repository.add_version(
        stored_template, pipeline.finalize(result.draft), result.assets, result.source,
    )
    assert repository.current_version(stored_template).version == 2

    repository.restore(stored_template, 1)

    assert repository.current_version(stored_template).version == 3
    assert [v.version for v in repository.versions(stored_template)] == [3, 2, 1]


def test_the_version_dialog_inherits_the_template_config(qt_app, session: Session,
                                                         stored_template: int):
    """A new version must resolve placeholders against the original languages."""
    from app.gui.dialogs.template_import import TemplateImportDialog
    from app.services.template.repository import TemplateRepository

    dialog = TemplateImportDialog(session, template_id=stored_template)
    original = TemplateRepository(session).current_version(stored_template).config

    inherited = dialog._inherited_config(stored_template)

    assert inherited.primary_language == original["primary_language"]
    assert inherited.secondary_language == original.get("secondary_language")
    assert dialog.inherited_label.text()


def test_the_version_dialog_hides_the_inherited_fields(qt_app, session: Session,
                                                       stored_template: int):
    from app.gui.dialogs.template_import import TemplateImportDialog

    dialog = TemplateImportDialog(session, template_id=stored_template)

    assert not dialog.primary_combo.isVisibleTo(dialog)
    assert not dialog.name_edit.isVisibleTo(dialog)
    assert dialog.path_edit.isVisibleTo(dialog)


def test_the_import_dialog_still_shows_them_for_a_new_template(qt_app,
                                                               session: Session):
    from app.gui.dialogs.template_import import TemplateImportDialog

    dialog = TemplateImportDialog(session)

    assert dialog.primary_combo.isVisibleTo(dialog)
    assert not dialog.inherited_label.isVisibleTo(dialog)


def test_an_unloadable_template_reports_instead_of_failing_to_open(qt_app,
                                                                   session: Session):
    """A constructor that raises takes the whole dialog down."""
    from app.db.models.core.template import Template
    from app.gui.dialogs.template_import import TemplateImportDialog

    template = Template(name="Versionless", type="invoice")
    session.add(template)
    session.commit()

    dialog = TemplateImportDialog(session, template_id=template.id)

    assert dialog.banner.text()
    assert not dialog.path_edit.isEnabled()


def test_the_template_edit_dialog_loads_and_fixes_languages(qt_app, session: Session,
                                                            stored_template: int):
    from app.gui.dialogs.template_edit import TemplateEditDialog

    dialog = TemplateEditDialog(session, stored_template)

    assert dialog.name_edit.text()
    assert dialog.type_combo.code() == "invoice"
    assert "re-import" in dialog.languages_label.text().lower()
    assert not dialog.languages_label.isEnabled()


def test_editing_a_template_renames_it(qt_app, session: Session, stored_template: int):
    from app.gui.dialogs.template_edit import TemplateEditDialog
    from app.services.template.repository import TemplateRepository

    dialog = TemplateEditDialog(session, stored_template)
    dialog.name_edit.setText("Renamed")
    dialog._save()

    assert TemplateRepository(session).get(stored_template).name == "Renamed"


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


@pytest.fixture
def stored_template(session: Session, make_docx, fixture_provider) -> int:
    """A real template with a version — a bare Template row cannot be loaded, so
    the columns rightly refuse it."""
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
    from app.services.template.repository import TemplateRepository

    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(make_docx(paragraphs=["Invoice for {{ org_name }}"]))
    blueprint = pipeline.finalize(result.draft)

    return TemplateRepository(session).create(blueprint, result.assets, result.source)


def test_revalidate_keeps_a_surviving_template(window, session: Session,
                                               stored_template: int):
    window.draft.set_template(stored_template, "invoice", ("ENG",))
    window.template_column.revalidate()

    assert window.draft.template_id == stored_template


def test_an_unloadable_template_is_dropped_rather_than_crashing(window,
                                                                session: Session):
    """A Template row with no version cannot render; selecting it must not raise
    inside a Qt slot, where the exception would vanish into stderr."""
    from app.db.models.core.template import Template

    template = Template(name="Versionless", type="invoice")
    session.add(template)
    session.commit()

    window.draft.set_template(template.id, "invoice", ("ENG",))
    window.template_column.revalidate()

    assert window.draft.template_id is None
    assert "cannot be loaded" in window.template_column.ui.details_label.text().lower()


# --- column edit and delete buttons ------------------------------------------

def select_organization(column, fragment: str) -> None:
    column.refresh_organizations()
    widget = column.ui.organization_list
    for position in range(widget.count()):
        if fragment.lower() in widget.item(position).text().lower():
            widget.setCurrentRow(position)
            return
    raise AssertionError(f"{fragment} not listed")


def confirm(monkeypatch, answer: bool) -> None:
    from PySide6.QtWidgets import QMessageBox

    button = (
        QMessageBox.StandardButton.Yes if answer else QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: button))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))


def test_organization_buttons_need_a_selection(window, make_org):
    column = window.provider_column

    assert not column.ui.edit_organization_button.isEnabled()
    assert not column.ui.delete_organization_button.isEnabled()

    make_org("Acme")
    select_organization(column, "Acme")

    assert column.ui.edit_organization_button.isEnabled()
    assert column.ui.delete_organization_button.isEnabled()


def test_template_buttons_need_a_selection(window, stored_template: int):
    column = window.template_column

    assert not column.ui.edit_template_button.isEnabled()
    assert not column.ui.delete_template_button.isEnabled()

    column.refresh()
    column.ui.template_list.setCurrentRow(0)

    assert column.ui.edit_template_button.isEnabled()
    assert column.ui.delete_template_button.isEnabled()


def test_deleting_an_organization_clears_the_draft(window, make_org, monkeypatch):
    organization = make_org("Acme")
    column = window.provider_column
    select_organization(column, "Acme")
    assert window.draft.provider_organization_id == organization.id

    confirm(monkeypatch, True)
    column._delete_organization()

    assert window.draft.provider_organization_id is None
    assert window.draft.provider_tax_id is None


def test_deleting_in_one_column_refreshes_the_other(window, make_org, monkeypatch):
    """The reason catalog_changed exists: Client lists the same organizations."""
    make_org("Acme")
    make_org("Globex", tax_value="22222222")

    provider, client = window.provider_column, window.client_column
    select_organization(provider, "Acme")
    select_organization(client, "Globex")
    assert client.ui.organization_list.count() == 2

    confirm(monkeypatch, True)
    provider._delete_organization()

    listed = [
        client.ui.organization_list.item(i).text()
        for i in range(client.ui.organization_list.count())
    ]
    assert len(listed) == 1
    assert "Globex" in listed[0]
    assert window.draft.client_organization_id is not None    # untouched


def test_deleting_the_organization_the_other_column_selected_clears_it(
        window, make_org, monkeypatch):
    make_org("Acme")
    provider, client = window.provider_column, window.client_column
    select_organization(provider, "Acme")
    select_organization(client, "Acme")          # both sides, same organization

    confirm(monkeypatch, True)
    provider._delete_organization()

    assert window.draft.provider_organization_id is None
    assert window.draft.client_organization_id is None


def test_declining_the_confirmation_deletes_nothing(window, make_org, monkeypatch):
    organization = make_org("Acme")
    column = window.provider_column
    select_organization(column, "Acme")

    confirm(monkeypatch, False)
    column._delete_organization()

    assert window.draft.provider_organization_id == organization.id


def test_a_built_in_template_refuses_deletion(window, session: Session,
                                              make_docx, fixture_provider,
                                              monkeypatch):
    """The repository refuses; the column must report it, not crash."""
    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
    from app.services.template.repository import TemplateRepository

    pipeline = TemplateIngestionPipeline(fixture_provider)
    result = pipeline.ingest(make_docx(paragraphs=["A {{ org_name }}"]))
    template_id = TemplateRepository(session).create(
        pipeline.finalize(result.draft), result.assets, result.source,
        code="default_invoice", system=True,
    )

    column = window.template_column
    column.refresh()
    column.ui.template_list.setCurrentRow(0)
    assert window.draft.template_id == template_id

    warnings: list = []
    confirm(monkeypatch, True)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: warnings.append(text)),
    )
    column._delete_template()

    assert warnings, "the refusal must be reported, not swallowed"
    assert window.draft.template_id == template_id       # still selected
    assert TemplateRepository(session).get(template_id) is not None


# --- editing an organization's sub-assets ------------------------------------

@pytest.fixture
def organization_with_details(session: Session, make_org):
    """An organization whose bank account has English names only — the state
    that had no way forward before update_bank_account existed."""
    from app.services.organization.repository import BankText, OrganizationRepository

    organization = make_org("Acme", with_bank=False)
    repository = OrganizationRepository(session)
    account = repository.add_bank_account(
        organization.id,
        iban="UA1", currency="UAH", country="UKR",
        localizations={"ENG": BankText(bank_name="PrivatBank", bank_info=None)},
    )

    return organization, organization.tax_ids[0], account


def test_the_bank_dialog_loads_an_account_for_editing(qt_app, session: Session,
                                                      organization_with_details):
    from app.gui.dialogs.bank_account import BankAccountDialog

    organization, _, account = organization_with_details
    dialog = BankAccountDialog(session, organization.id, account.id)

    assert dialog.iban_edit.text() == "UA1"
    assert dialog.currency_combo.code() == "UAH"
    assert dialog.country_combo.code() == "UKR"
    assert dialog.localizations._edits["ENG"]["bank_name"].text() == "PrivatBank"


def test_the_bank_dialog_can_add_the_missing_language(qt_app, session: Session,
                                                      organization_with_details):
    from app.gui.dialogs.bank_account import BankAccountDialog
    from app.services.organization.repository import OrganizationRepository

    organization, _, account = organization_with_details
    dialog = BankAccountDialog(session, organization.id, account.id)

    dialog.localizations._add_tab("UKR")
    dialog.localizations._edits["UKR"]["bank_name"].setText("ПриватБанк")
    dialog._save()

    stored = OrganizationRepository(session).get(organization.id).bank_accounts[0]
    assert stored.id == account.id                  # edited, not replaced
    assert stored.localizations["UKR"].bank_name == "ПриватБанк"


def test_the_tax_dialog_loads_an_identifier_for_editing(qt_app, session: Session,
                                                        organization_with_details):
    from app.gui.dialogs.tax_id import TaxIdDialog

    organization, tax_id, _ = organization_with_details
    dialog = TaxIdDialog(session, organization.id, tax_id.id)

    assert dialog.value_edit.text() == tax_id.value
    assert dialog.system_combo.code() == "ua_edrpou"


def test_editing_a_tax_id_keeps_its_identity(qt_app, session: Session,
                                             organization_with_details):
    from app.gui.dialogs.tax_id import TaxIdDialog

    organization, tax_id, _ = organization_with_details
    dialog = TaxIdDialog(session, organization.id, tax_id.id)

    dialog.value_edit.setText("99999999")
    dialog._save()

    assert dialog.tax_id_id == tax_id.id
    assert tax_id.value == "99999999"


def test_edit_buttons_need_something_selected(window, organization_with_details):
    column = window.provider_column

    assert not column.ui.edit_tax_button.isEnabled()
    assert not column.ui.edit_bank_button.isEnabled()
    assert not column.ui.edit_representative_button.isEnabled()

    column.refresh_organizations()
    widget = column.ui.organization_list
    for position in range(widget.count()):
        if "Acme" in widget.item(position).text():
            widget.setCurrentRow(position)
            break

    assert column.ui.edit_tax_button.isEnabled()    # a lone tax id auto-selects
    assert not column.ui.edit_bank_button.isEnabled()


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


# --- the settings dialog -----------------------------------------------------

@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATER_SETTINGS", str(tmp_path / "plater.ini"))
    return tmp_path / "plater.ini"


def test_the_settings_dialog_loads_both_stores(qt_app, session: Session,
                                               seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog

    dialog = SettingsDialog(session)

    assert dialog.language_combo.currentData() == "ENG"      # the ini
    assert dialog.primary_combo.code() == "ENG"              # the database
    assert dialog.type_combo.code() == "invoice"
    assert dialog.name_edit.text()


def test_settings_widgets_are_all_in_a_layout(qt_app, session: Session,
                                              seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog

    assert orphans(SettingsDialog(session)) == []


def test_saving_the_language_writes_the_file(qt_app, session: Session,
                                             seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog
    from app.gui.settings import ui_language

    dialog = SettingsDialog(session)
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("UKR"))
    dialog._save()

    assert dialog.language_changed
    assert ui_language() == "UKR"


def test_leaving_the_language_alone_reports_no_change(qt_app, session: Session,
                                                      seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog

    dialog = SettingsDialog(session)
    dialog._save()

    assert not dialog.language_changed


def test_saving_updates_the_template_defaults(qt_app, session: Session,
                                              seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog
    from app.services.settings import TemplateDefaultService

    dialog = SettingsDialog(session)
    dialog.name_edit.setText("Rakhunok")
    dialog.currency_check.setChecked(False)
    dialog._save()

    row = TemplateDefaultService(session).get()
    assert row.name == "Rakhunok"
    assert row.append_currency is False


def test_the_secondary_language_can_be_cleared(qt_app, session: Session,
                                               seeded_inputs, settings_file):
    from app.gui.dialogs.settings import SettingsDialog
    from app.services.settings import TemplateDefaultService

    dialog = SettingsDialog(session)
    dialog.secondary_combo.set_code("")
    dialog._save()

    assert TemplateDefaultService(session).get().secondary_language_code is None


def test_a_rejected_default_leaves_the_language_file_untouched(qt_app,
                                                               session: Session,
                                                               seeded_inputs,
                                                               settings_file):
    """The database write runs first, so a refused update must not half-save."""
    from app.gui.dialogs.settings import SettingsDialog
    from app.gui.settings import ui_language

    dialog = SettingsDialog(session)
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("UKR"))
    dialog.secondary_combo.set_code("ENG")           # same as primary: refused

    dialog._save()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.banner.text()
    assert ui_language() == "ENG"                    # not written
    assert not dialog.language_changed


def test_an_incomplete_form_is_refused(qt_app, session: Session, seeded_inputs,
                                       settings_file):
    from app.gui.dialogs.settings import SettingsDialog

    dialog = SettingsDialog(session)
    dialog.name_edit.setText("   ")
    dialog._save()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.banner.text()


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


# --- 2026-09-04 manual test pass: open tasks ---------------------------------
#
# Each xfail(strict=True) below is an open task. Fixing it turns the test into an
# XPASS failure, which is the signal to drop the marker.

TASK = "open task from the 2026-09-04 manual test pass"


def test_browsing_for_a_template_fills_the_path(qt_app, session: Session, monkeypatch,
                                                seeded_inputs, make_docx):
    """File > Browse opened the picker and then threw the choice away."""
    from PySide6.QtWidgets import QFileDialog
    from app.gui.dialogs.template_import import TemplateImportDialog

    chosen = make_docx(paragraphs=["Invoice for {{ org_name }}"])
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(chosen), "")),
    )

    dialog = TemplateImportDialog(session)
    dialog._browse()

    assert dialog.path_edit.text() == str(chosen)


def test_cancelling_the_browse_dialog_changes_nothing(qt_app, session: Session,
                                                      monkeypatch, seeded_inputs):
    from PySide6.QtWidgets import QFileDialog
    from app.gui.dialogs.template_import import TemplateImportDialog

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")),
    )

    dialog = TemplateImportDialog(session)
    dialog._browse()

    assert dialog.path_edit.text() == ""


def test_refreshing_sequences_keeps_the_selected_one_visible(window, session: Session,
                                                             make_org, make_sequence,
                                                             stored_template: int):
    """After a generate the combo repopulates. It used to come back blank while
    DraftState still held the sequence, so the two disagreed on screen.
    """

    column = window.provider_column
    organization = make_org("Acme")
    make_sequence(organization, prefix="INV-")
    make_sequence(organization, prefix="ACT-")

    window.draft.set_template(stored_template, "invoice", ("ENG",))
    select_organization(column, "Acme")
    column.ui.sequence_combo.setCurrentIndex(0)
    selected = window.draft.sequence_id

    assert selected is not None, "picking a prefix must reach the draft"

    column.refresh_sequences()

    assert window.draft.sequence_id == selected
    assert column.ui.sequence_combo.currentIndex() >= 0
    assert column.ui.sequence_combo.currentData() == selected


def bilingual_column_provider():
    """A provider knowing invl_desc as a COLUMN in two languages."""
    from app.document_engine.blueprint.models.template import TemplateConfig
    from app.document_engine.enums.enums import PlaceholderType
    from tests.conftest import FixtureInputProvider

    return FixtureInputProvider(
        placeholders={
            "org_name": {"active": True, "required": True, "type": PlaceholderType.SCALAR},
            "invl_desc": {"active": True, "required": True, "type": PlaceholderType.COLUMN},
        },
        config=TemplateConfig(
            primary_language="ENG",
            secondary_language="UKR",
            type="invoice",
            name="bilingual",
            description="",
            append_currency=False,
        ),
    )


@pytest.fixture
def bilingual_template(session: Session, make_docx):
    """A template whose v1 renders descriptions in ENG only, plus a factory that
    appends a v2 placing the UKR column too."""

    from app.document_engine.orchestration.pipeline import TemplateIngestionPipeline
    from app.services.template.repository import TemplateRepository

    provider = bilingual_column_provider()
    repository = TemplateRepository(session)

    def ingest(table):
        pipeline = TemplateIngestionPipeline(provider)
        result = pipeline.ingest(make_docx(table=table, name=f"v{len(table[0])}.docx"))
        return pipeline.finalize(result.draft), result.assets, result.source

    blueprint, assets, source = ingest([["{{ invl_desc.ENG }}"]])
    template_id = repository.create(blueprint, assets, source)

    def add_secondary_version() -> None:
        blueprint, assets, source = ingest(
            [["{{ invl_desc.ENG }}", "{{ invl_desc.UKR }}"]]
        )
        repository.add_version(template_id, blueprint, assets, source)

    return template_id, add_secondary_version


def test_a_new_template_version_updates_the_description_columns(window, session: Session,
                                                                bilingual_template):
    """Adding a version that places {{ invl_desc.UKR }} must give the lines grid a
    second description column. The id does not change, so the cache never expired
    and only a restart picked it up.
    """

    template_id, add_secondary_version = bilingual_template
    column = window.document_column

    window.draft.set_template(template_id, "invoice", ("ENG", "UKR"))
    assert column._grid_languages() == ("ENG",)

    add_secondary_version()
    window._revalidate_columns()

    assert column._grid_languages() == ("ENG", "UKR")


def test_revalidating_the_document_column_without_a_template_is_a_no_op(window):
    """_revalidate_columns() now reaches this column, and it fires on any manager
    change — including before a template has ever been picked."""

    window.document_column.revalidate()

    assert window.document_column._grid_languages() == ()
    assert not window.document_column.ui.add_button.isEnabled()


def test_a_template_declaring_a_language_it_never_places_stays_single(window,
                                                                     bilingual_template):
    """The other half of the same report, and this one is correct behaviour:
    languages come from what the blueprint renders, not from the config.
    """

    template_id, _ = bilingual_template
    window.draft.set_template(template_id, "invoice", ("ENG", "UKR"))

    assert window.document_column._grid_languages() == ("ENG",)
