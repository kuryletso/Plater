from __future__ import annotations

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
    edit: Callable[[QWidget, AssetId], bool]
    delete: Callable[[AssetId], None]
    delete_verb: str = "Delete"


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

        self.list = QListWidget()
        self.banner = ErrorBanner()

        self.new_button = QPushButton("New...")
        self.edit_button = QPushButton("Edit...")
        self.delete_button = QPushButton(asset.delete_verb)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0,0,0,0)
        actions_layout.addWidget(self.new_button)
        actions_layout.addWidget(self.edit_button)
        actions_layout.addWidget(self.delete_button)
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
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)

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
        has_selection = self._selected() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)


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
            self._asset.delete(item.data(Qt.ItemDataRole.UserRole))
        except ServiceError as e:
            self.banner.show_message(e.user_message or str(e))
            return

        self.changed = True
        self.refresh()