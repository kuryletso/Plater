from __future__ import annotations

from PySide6.QtWidgets import QWidget, QDialog, QInputDialog
from sqlalchemy.orm import Session

from app.gui.dialogs.manager_dialog import AssetId, AssetAction, ManagedAsset, ManagerDialog
from app.gui.dialogs.organization import OrganizationDialog
from app.gui.dialogs.template_import import TemplateImportDialog
from app.gui.dialogs.template_edit import TemplateEditDialog
from app.gui.dialogs.representative import RepresentativeDialog
from app.gui.dialogs.measurement_unit import MeasurementUnitDialog
from app.gui.text import organization_label, localized
from app.services.organization.repository import OrganizationRepository
from app.services.template.repository import TemplateRepository
from app.services.representative.repository import RepresentativeRepository
from app.services.measurement_unit.repository import MeasurementUnitRepository
from app.services.errors import ServiceError


def organization_asset(session: Session) -> ManagedAsset:
    repository = OrganizationRepository(session)

    def list_items(search: str | None) -> list[tuple[AssetId, str]]:
        return [
            (organization.id, organization_label(organization))
            for organization in repository.list(search=search)
        ]


    def create(parent: QWidget) -> AssetId | None:
        dialog = OrganizationDialog(session, parent=parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        return dialog.organization_id


    def edit(parent: QWidget, asset_id: AssetId) -> bool:
        dialog = OrganizationDialog(session, int(asset_id), parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted


    def delete(asset_id: AssetId) -> None:
        repository.delete(int(asset_id))


    return ManagedAsset(
        title="Organization",
        list_items=list_items,
        create=create,
        edit=edit,
        delete=delete,
    )


def template_asset(session: Session) -> ManagedAsset:
    repository = TemplateRepository(session)

    def versions(parent: QWidget, asset_id: AssetId) -> bool:
        dialog = ManagerDialog(
            template_version_asset(session, int(asset_id)),
            parent=parent,
        )
        dialog.exec()
        return dialog.changed

    def list_items(search: str | None) -> list[tuple[AssetId, str]]:
        return [
            (
                template.id,
                f"{template.name} ({template.type})"
                + ("  | built-in" if template.system else "")
                + ("  | hidden" if not template.active else ""),
            )
            for template in repository.list(search=search, include_inactive=True)
        ]

    def create(parent):
        dialog = TemplateImportDialog(session, parent=parent)
        return dialog.template_id if dialog.exec() == QDialog.DialogCode.Accepted else None


    def duplicate(parent: QWidget, asset_id: AssetId) -> bool:
        origin = next(
            template for template in repository.list(include_inactive=True)
            if template.id == int(asset_id)
        )

        name, accepted = QInputDialog.getText(
            parent, "Duplicate template", "Name:", text=f"{origin.name} (copy)",
        )
        if not accepted or not name.strip():
            return False
        
        repository.copy(int(asset_id), name.strip())
        return True

    def toggle(parent: QWidget, asset_id: AssetId) -> bool:
        template = repository.get(template_id=int(asset_id))
        
        if template.active:
            repository.deactivate(template.id)
        else:
            repository.activate(template.id)
        return True

    def toggle_label(asset_id: AssetId | None) -> str:
        return "Hide" \
            if asset_id is None or repository.get(int(asset_id)).active \
            else "Show again"

    def edit(parent: QWidget, asset_id: AssetId) -> bool:
        dialog = TemplateEditDialog(session, int(asset_id), parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    return ManagedAsset(
        title="Templates",
        list_items=list_items,
        create=create,
        edit=edit,
        actions=(
            AssetAction(label="Versions...", run=versions),
            AssetAction(label="Duplicate", run=duplicate),
            AssetAction(label=toggle_label, run=toggle),
        ),
        delete=lambda asset_id: repository.delete(int(asset_id)),
    )


def representative_asset(session: Session) -> ManagedAsset:
    repository= RepresentativeRepository(session)

    def list_items(search):
        rows = []
        for person in repository.list(search=search):
            name = localized(person.localizations, "name")
            title = localized(person.localizations, "title")
            attached = len(person.organizations)
            label = f"{name} — {title}" if title != "?" else name
            rows.append((person.id, f"{label} ({attached} organization(s))"))
        return rows


    def create(parent):
        dialog = RepresentativeDialog(session, parent=parent)
        return dialog.representative_id if dialog.exec() == QDialog.DialogCode.Accepted else None


    def edit(parent, asset_id):
        dialog = RepresentativeDialog(session, representative_id=int(asset_id), parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted


    return ManagedAsset(
        title="Representative",
        list_items=list_items,
        create=create,
        edit=edit,
        delete=lambda asset_id: repository.delete(int(asset_id)),
    )


def measurement_unit_asset(session: Session) -> ManagedAsset:
    repository = MeasurementUnitRepository(session)

    def list_items(search: str | None) -> list[tuple[AssetId, str]] :
        return [
            (
                unit.code,
                f"{localized(unit.localizations, 'name')} ({unit.code})"
                + ("  | hidden" if not unit.active else ""),
            )
            for unit in repository.list(search=search, include_inactive=True)
        ]

    def create(parent):
        dialog = MeasurementUnitDialog(session, parent=parent)
        return dialog.unit_code if dialog.exec() == QDialog.DialogCode.Accepted else None

    def edit(parent, asset_id):
        dialog = MeasurementUnitDialog(session, unit_code=str(asset_id), parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def toggle(parent: QWidget, asset_id: AssetId) -> bool:
        unit = repository.get(str(asset_id))
        if unit.active:
            repository.deactivate(unit.code)
        else:
            repository.activate(unit.code)
        return True

    def toggle_label(asset_id: AssetId | None) -> str:
        return "Hide" \
            if asset_id is None or repository.get(str(asset_id)).active \
            else "Show again"

    return ManagedAsset(
        title="Measurement units",
        list_items=list_items,
        create=create,
        edit=edit,
        actions=(AssetAction(label=toggle_label, run=toggle),),
        delete=None,
        delete_verb="Hide",
    )


def template_version_asset(session: Session, template_id: int) -> ManagedAsset:
    repository = TemplateRepository(session)

    def list_items(search) -> list[tuple[AssetId, str]]:
        current = repository.current_version(template_id).version

        return [
            (
                version.version,
                f"Version {version.version} — "
                f"{version.created_at:%Y-%m-%d %H:%M}"
                + (" | current" if version.version == current else ""),
            )
            for version in repository.versions(template_id)
        ]

    def create(parent: QWidget) -> AssetId | None:
        dialog = TemplateImportDialog(
            session=session,
            template_id=template_id,
            parent=parent,
        )
        return dialog.version if dialog.exec() == QDialog.DialogCode.Accepted else None

    def restore(parent: QWidget, asset_id: AssetId) -> bool:
        repository.restore(template_id, int(asset_id))
        return True

    return ManagedAsset(
        title=f"Versions of {repository.get(template_id).name}",
        list_items=list_items,
        create=create,
        edit=None,
        delete=None,
        actions=(AssetAction(label="Restore", run=restore),),
        searchable=False,
    )