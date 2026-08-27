from __future__ import annotations

from PySide6.QtWidgets import QWidget, QDialog
from sqlalchemy.orm import Session

from app.gui.dialogs.manager_dialog import AssetId, ManagedAsset
from app.gui.dialogs.organization import OrganizationDialog
from app.gui.text import organization_label
from app.services.organization.repository import OrganizationRepository


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