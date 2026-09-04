from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import QListWidgetItem, QWidget, QDialog, QMessageBox
from sqlalchemy.orm import Session

from app.gui.generated.ui_template_column import Ui_TemplateColumn
from app.services.template.repository import TemplateRepository
from app.gui.draft_state import DraftState
from app.gui.dialogs.template_import import TemplateImportDialog
from app.gui.dialogs.template_edit import TemplateEditDialog
from app.services.errors import ServiceError
from app.db.models.core.template_version import TemplateVersion


class TemplateColumn(QWidget):
    """Pick the template. Its document type will drive sequence filtering."""

    catalog_changed = Signal()

    def __init__(
            self,
            session: Session,
            draft: DraftState,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._draft = draft
        self._session = session
        self._repo = TemplateRepository(session)

        self.ui = Ui_TemplateColumn()
        self.ui.setupUi(self)

        self.ui.search_edit.textChanged.connect(self.refresh)
        self.ui.template_list.currentItemChanged.connect(self._on_selection)
        self.ui.add_template_button.clicked.connect(self._import_template)
        self.ui.edit_template_button.clicked.connect(self._edit_template)
        self.ui.delete_template_button.clicked.connect(self._delete_template)
        self.ui.clear_button.clicked.connect(self.clear_selection)
        self._show_selected(None)

        self.refresh()


    def refresh(self) -> None:
        """Filtering is a view change. Selection lives in DraftState and survives it."""

        search = self.ui.search_edit.text().strip() or None
        selected = self._draft.template_id

        widget = self.ui.template_list
        with QSignalBlocker(widget):
            widget.clear()
            templates = self._repo.list(search=search)
            for template in templates:
                item = QListWidgetItem(template.name)
                item.setData(Qt.ItemDataRole.UserRole, (template.id, template.type))
                if template.system:
                    item.setToolTip("Built-in template")
                widget.addItem(item)

                if template.id == selected:
                    widget.setCurrentItem(item)

            if not templates:
                self._show_empty_notice(search)


    def clear_selection(self) -> None:
        with QSignalBlocker(self.ui.template_list):
            self.ui.template_list.setCurrentRow(-1)

        self.ui.details_label.setText("")
        self._draft.set_template(None, None, ())
        self._show_selected(None)


    def revalidate(self) -> None:
        """Drops a selection that no longer exists if assets changed elsewhere."""

        template_id = self._draft.template_id
        if template_id is not None and template_id not in {
            template.id for template in self._repo.list(include_inactive=True)
        }:
            self.clear_selection()

        self.refresh()

        current = self.ui.template_list.currentItem()
        if current is not None:
            self._on_selection(current)


    def _on_selection(
            self,
            current: QListWidgetItem | None,
            _previous: QListWidgetItem | None = None,
    ) -> None:
        
        if current is None:
            self.ui.details_label.setText("")
            self._draft.set_template(None, None, ())
            return

        self._show_selected(current.text())
        template_id, document_type = current.data(Qt.ItemDataRole.UserRole)

        try:
            version = self._repo.current_version(template_id)
        except ServiceError as e:
            # an exception escaping a slot is swallowed by Qt
            self.ui.details_label.setText(
                f"<b>This template cannot be loaded.</b><br>"
                f"{escape(e.user_message or str(e))}"
            )
            self._draft.set_template(None, None, ())
            return
        
        config = version.config
        languages = tuple(
            code for code
            in (config.get("primary_language"), config.get("secondary_language"))
            if code
        )

        self._show_details(version)
        self._draft.set_template(template_id, document_type, languages)
        

    def _show_details(self, version: TemplateVersion) -> None:
        config = version.config

        languages = " / ".join(
            code for code
            in (config.get("primary_language"), config.get("secondary_language"))
            if code
        )
        description = escape(config.get("description") or "") or "--"

        self.ui.details_label.setText(
            f"<b>Type:</b> {escape(config.get('type', '?'))}<br>"
            f"<b>Languages:</b> {languages}<br>"
            f"<b>Version:</b> {version.version}<br>"
            f"<b>Description:</b> {description}"
        )


    def _show_selected(self, name: str | None) -> None:
        self.ui.selection_label.setText(name or "Nothing selected")
        self.ui.selection_label.setEnabled(name is not None)
        self.ui.edit_template_button.setEnabled(name is not None)
        self.ui.delete_template_button.setEnabled(name is not None)
        self.ui.clear_button.setEnabled(name is not None)


    def _show_empty_notice(self, search: str | None) -> None:
        item = QListWidgetItem(
            f'No matches for "{search}"' if search else "No templates yet"
        )
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui.template_list.addItem(item)


    def _import_template(self) -> None:
        dialog = TemplateImportDialog(self._session, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.refresh()
        for position in range(self.ui.template_list.count()):
            item = self.ui.template_list.item(position)
            if item.data(Qt.ItemDataRole.UserRole)[0] == dialog.template_id:
                self.ui.template_list.setCurrentRow(position)
                break

        self.catalog_changed.emit()


    def _edit_template(self) -> None:
        template_id = self._draft.template_id
        if template_id is None:
            return

        dialog = TemplateEditDialog(self._session, template_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.catalog_changed.emit()


    def _delete_template(self) -> None:
        template_id = self._draft.template_id
        if template_id is None:
            return

        confirmed = QMessageBox.question(
            self, "Delete tempalte",
            f'Delete "{self.ui.selection_label.text()}"?',
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            self._repo.delete(template_id)
        except ServiceError as e:
            QMessageBox.warning(
                self, "Cannot delete",
                e.user_message or str(e),
            )
            return

        self.catalog_changed.emit()