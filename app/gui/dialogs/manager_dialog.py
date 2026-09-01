from __future__ import annotations

from typing import cast

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
)

from app.gui.dialogs.widgets import ErrorBanner
from app.services.errors import ServiceError

AssetId = int | str


@dataclass(slots=True, frozen=True)
class ManagedAsset:
    title: str
    list_items: Callable[[str | None], list[tuple[AssetId,str]]]
    create: Callable[[QWidget], AssetId | None]
    edit: Callable[[QWidget, AssetId], bool] | None = None
    delete: Callable[[AssetId], None] | None = None
    actions: tuple[AssetAction, ...] = ()
    delete_verb: str = "Delete"
    searchable: bool = True


@dataclass(slots=True, frozen=True)
class AssetAction:
    """One extra button. The label may depend on the selection."""

    label: str | Callable[[AssetId | None], str]
    run: Callable[[QWidget, AssetId], bool]

    def text(self, asset_id: AssetId | None) -> str:
        return self.label if isinstance(self.label, str) else self.label(asset_id)


class ManagerDialog(QDialog):
    """List of one asset kind with New, Edit and Delete options."""

    def __init__(
            self,
            asset: ManagedAsset,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._asset = asset
        self.changed = False

        self.setWindowTitle(asset.title)
        self.setMinimumSize(520, 420)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setVisible(asset.searchable)

        self.list = QListWidget()
        self.banner = ErrorBanner()

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0,0,0,0)

        self.new_button = QPushButton("New...")

        self.edit_button = QPushButton("Edit...") if asset.edit is not None else None
        if self.edit_button is not None:
            self.edit_button.clicked.connect(self._edit)
            actions_layout.addWidget(self.edit_button)

        self._extra_buttons: list[QPushButton] = []
        for action in asset.actions:
            button = QPushButton(action.text(None) if isinstance(action.label, str) else "")
            button.clicked.connect(lambda *_, run=action.run: self._run_extra(run))
            actions_layout.addWidget(button)
            self._extra_buttons.append(button)

        self.delete_button = QPushButton(asset.delete_verb) if asset.delete else None
        if self.delete_button is not None:
            self.delete_button.clicked.connect(self._delete)
            actions_layout.addWidget(self.delete_button)

        actions_layout.addWidget(self.new_button)
        actions_layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list, 1)
        layout.addWidget(actions)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self.search_edit.textChanged.connect(self.refresh)
        self.list.currentItemChanged.connect(self._update_actions)
        self.list.itemDoubleClicked.connect(self._edit)
        self.new_button.clicked.connect(self._create)

        self.refresh()


    def refresh(self, select: AssetId | None = None) -> None:
        search = self.search_edit.text().strip() or None
        keep = select if select is not None else self._selected()

        self.list.clear()
        for asset_id, label in self._asset.list_items(search):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, asset_id)
            self.list.addItem(item)

            if asset_id == keep:
                self.list.setCurrentItem(item)

        self._update_actions()


    def _selected(self) -> AssetId | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None


    def _update_actions(self) -> None:
        asset_id = self._selected()
        has_selection = asset_id is not None

        if self.edit_button is not None:
            self.edit_button.setEnabled(has_selection)
        if self.delete_button is not None:
            self.delete_button.setEnabled(has_selection)


        for button, action in zip(self._extra_buttons, self._asset.actions):
            button.setEnabled(has_selection)
            button.setText(action.text(asset_id))



    def _create(self) -> None:
        self.banner.clear_message()

        created = self._asset.create(self)
        if created is not None:
            self.changed = True
            self.refresh(select=created)


    def _edit(self) -> None:
        self.banner.clear_message()

        asset_id = self._selected()
        if asset_id is None:
            return

        if self._asset.edit is None:
            return

        if self._asset.edit(self, asset_id):
            self.changed = True
            self.refresh(select=asset_id)


    def _delete(self) -> None:
        self.banner.clear_message()

        item = self.list.currentItem()
        if item is None:
            return

        confirmed = QMessageBox.question(
            self,
            self._asset.delete_verb,
            f'{self._asset.delete_verb} "{item.text().splitlines()[0]}"?',
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return


        try:
            if self._asset.delete is not None:      # for static type checking, self._delete() is only called if self._asset.delete isn't None
                self._asset.delete(item.data(Qt.ItemDataRole.UserRole))
        except ServiceError as e:
            self.banner.show_message(e.user_message or str(e))
            return

        self.changed = True
        self.refresh()


    def _run_extra(self, action) -> None:
        self.banner.clear_message()

        asset_id = self._selected()
        if asset_id is None:
            return

        try:
            changed = action(self, asset_id)
        except ServiceError as e:
            self.banner.show_message(e.user_message or str(e))
            return

        if changed:
            self.changed = True
            self.refresh()