from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QLineEdit,
    QVBoxLayout,
)
from sqlalchemy.orm import Session

from app.gui.dialogs.widgets import (
    ErrorBanner,
    document_type_items,
    searchable_combo,
    selected_code,
    show_code,
)
from app.services.doc_sequence.repository import SequenceRepository
from app.services.errors import ServiceError


class SequenceDialog(QDialog):
    """Numbering sequence for one organization and document type."""

    def __init__(
            self,
            session: Session,
            organization_id: int,
            document_type: str | None = None,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = SequenceRepository(session)
        self._organization_id = organization_id
        self.sequence_id: int | None = None

        self.setWindowTitle("New numbering sequence")
        self.setMinimumWidth(440)

        self.type_combo = searchable_combo(document_type_items(session))
        show_code(self.type_combo, document_type)

        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("INV-")

        self.counter_spin = QSpinBox()
        self.counter_spin.setMaximum(99_99_999)

        self.padding_spin = QSpinBox()
        self.padding_spin.setMaximum(12)
        self.padding_spin.setValue(5)

        self.preview_label = QLabel()
        self.preview_label.setEnabled(False)
        self.banner = ErrorBanner()

        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0,0,0,0)
        form.addRow("Document type", self.type_combo)
        form.addRow("Prefix", self.prefix_edit)
        form.addRow("Last issued number", self.counter_spin)
        form.addRow("Digits", self.padding_spin)
        form.addRow("", self.preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(fields)
        layout.addWidget(self.banner)
        layout.addWidget(buttons)

        self.prefix_edit.textChanged.connect(self._refresh_preview)
        self.counter_spin.valueChanged.connect(self._refresh_preview)
        self.padding_spin.valueChanged.connect(self._refresh_preview)

        self._refresh_preview()


    def _refresh_preview(self) -> None:
        number = str(self.counter_spin.value() + 1).zfill(self.padding_spin.value())
        self.preview_label.setText(
            f"Next document: {self.prefix_edit.text().strip()}{number}"
        )


    def _save(self) -> None:
        self.banner.clear_message()

        document_type = selected_code(self.type_combo)
        if document_type is None:
            self.banner.show_message("Choose a document_type")
            return

        try:
            created = self._repo.create(
                self._organization_id,
                document_type,
                prefix=self.prefix_edit.text().strip() or None,
                counter=self.counter_spin.value(),
                padding=self.padding_spin.value(),
            )
        except ServiceError as error:
            self._session.rollback()
            self.banner.show_message(error.user_message or str(error))
            return
        
        self.sequence_id = created.id
        self.accept()