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
    """Numbering sequence for one organization and document type.
    
    With a sequence_id it edits sequence's prefix and digits. The document 
    type is fixed, and the counter stays with the provider column's 
    next-number field.
    """

    def __init__(
            self,
            session: Session,
            organization_id: int,
            document_type: str | None = None,
            parent: QWidget | None = None,
            *,
            sequence_id: int | None = None,
    ) -> None:

        super().__init__(parent)
        self._session = session
        self._repo = SequenceRepository(session)
        self._organization_id = organization_id
        self.sequence_id: int | None = sequence_id

        self.setWindowTitle(
            "Edit numbering sequence" if sequence_id is not None else "New numbering sequence"
        )
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

        if sequence_id is not None:
            self._load(sequence_id)

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

        prefix = self.prefix_edit.text().strip() or None

        try:
            if self.sequence_id is not None:
                self._repo.update(
                    self.sequence_id,
                    prefix=prefix,
                    padding=self.padding_spin.value(),
                )
            else:
                self.sequence_id = self._repo.create(
                    self._organization_id,
                    document_type,
                    prefix=prefix,
                    counter=self.counter_spin.value(),
                    padding=self.padding_spin.value(),
                ).id
        except ServiceError as error:
            self._session.rollback()
            self.banner.show_message(error.user_message or str(error))
            return
        
        self.accept()


    def _load(self, sequence_id: int) -> None:
        sequence = self._repo.get(sequence_id)

        show_code(self.type_combo, sequence.document_type_code)
        self.prefix_edit.setText(sequence.prefix or "")
        self.counter_spin.setValue(sequence.counter)
        self.padding_spin.setValue(sequence.padding)

        self.type_combo.setEnabled(False)
        self.counter_spin.setEnabled(False)
        self.counter_spin.setToolTip("Change the next number in the provider column.")