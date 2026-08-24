from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
)
from sqlalchemy.orm import Session

from app.gui.dialogs.widgets import ErrorBanner, LocalizedFields, default_languages
from app.gui.text import localized
from app.services.errors import ServiceError
from app.services.organization.repository import OrganizationRepository
from app.services.representative.repository import (
    RepresentativeRepository,
    RepresentativeText,
)

FIELDS = (
    ("name", "Name"),
    ("title", "Title"),
)

class RepresentativeDialog(QDialog):
    """Representatives are shared between organizations. This dialog both attached an existing one 
    and create a new one (in separate tabs).
    """

    def __init__(
            self,
            session: Session,
            organization_id: int,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = RepresentativeRepository(session)
        self._organizations = OrganizationRepository(session)
        self._organization_id = organization_id
        self.representative_id: int | None = None

        self.setWindowTitle("Add representative")
        self.setMinimumWidth(460)

        # existing representative
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search representative...")
        self.search_edit.setClearButtonEnabled(True)
        self.existing_list = QListWidget()

        existing = QWidget()
        existing_layout = QVBoxLayout(existing)
        existing_layout.addWidget(self.search_edit)
        existing_layout.addWidget(self.existing_list)

        # new representative
        self.localizations = LocalizedFields(session, FIELDS)

        self.tabs = QTabWidget()
        self.tabs.addTab(existing, "Existing")
        self.tabs.addTab(self.localizations, "New")

        self.banner = ErrorBanner()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self.search_edit.textChanged.connect(self._refresh_existing)
        self._refresh_existing()
        self.localizations.set_values(
            { code: {} for code in default_languages(session) }
        )


    def _refresh_existing(self) -> None:
        search = self.search_edit.text().strip() or None

        self.existing_list.clear()
        for representative in self._repo.list(search=search):
            label = localized(representative.localizations, "name")
            title = localized(representative.localizations, "title")
            item = QListWidgetItem(f"{label} — {title}" if title != "?" else label)
            item.setData(Qt.ItemDataRole.UserRole, representative.id)
            self.existing_list.addItem(item)


    def _save(self) -> None:
        self.banner.clear_message()

        try:
            if self.tabs.currentIndex() == 0:
                self.representative_id = self._chosen_existing()
            else:
                self.representative_id = self._create_new()

            if self.representative_id is None:
                return

            self._organizations.attach_representative(
                self._organization_id,
                self.representative_id,
            )

        except ServiceError as e:
            self._session.rollback()
            self.banner.show_message(e.user_message or str(e))
            return

        self.representative_id = self.representative_id
        self.accept()


    def _chosen_existing(self) -> int | None:
        item = self.existing_list.currentItem()
        if item is None:
            self.banner.show_message("Select a representative, or create a new one.")
            return None

        return item.data(Qt.ItemDataRole.UserRole)


    def _create_new(self) -> int | None:
        texts: dict[str, RepresentativeText] = {}

        for code, values in self.localizations.values().items():
            if not values.get("name"):
                self.banner.show_message(
                    f"{self.localizations.language_name(code)}: a name is required.",
                )
                return None

            texts[code] = RepresentativeText(
                name=values["name"],
                title=values.get("title") or None,
            )

        if not texts:
            self.banner.show_message("Enter a name in at least one language.")
            return None

        return self._repo.create(texts).id


    