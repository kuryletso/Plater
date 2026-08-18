from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidgetItem, QWidget
from sqlalchemy.orm import Session

from app.gui.generated.ui_template_column import Ui_TemplateColumn
from app.services.template.repository import TemplateRepository
from app.gui.draft_state import DraftState


class TemplateColumn(QWidget):
    """Pick the template. Its document type will drive sequence filtering."""

    def __init__(
            self,
            session: Session,
            draft: DraftState,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._draft = draft
        self._repo = TemplateRepository(session)

        self.ui = Ui_TemplateColumn()
        self.ui.setupUi(self)

        self.ui.search_edit.textChanged.connect(self.refresh)
        self.ui.template_list.currentItemChanged.connect(self._on_selection)

        self.refresh()


    def refresh(self) -> None:
        search = self.ui.search_edit.text().strip() or None

        self.ui.template_list.clear()
        for template in self._repo.list(search=search):
            item = QListWidgetItem(template.name)
            item.setData(Qt.ItemDataRole.UserRole, (template.id, template.type))
            if template.system:
                item.setToolTip("Built-in template")
            self.ui.template_list.addItem(item)


    def _on_selection(
            self,
            current: QListWidgetItem | None,
            _previous: QListWidgetItem | None = None,
    ) -> None:
        
        if current is None:
            self.ui.details_label.setText("")
            self._draft.set_template(None, None)
            return

        template_id, document_type = current.data(Qt.ItemDataRole.UserRole)
        self._show_details(template_id)
        self._draft.set_template(template_id, document_type)
        

    def _show_details(self, template_id: int) -> None:
        version = self._repo.current_version(template_id)
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