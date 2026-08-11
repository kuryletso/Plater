from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

class PreviewPanel(QFrame):
    """Placeholder. Becomes the live HTML preview when the html emitter lands."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        label = QLabel("Preview feature is coming soon.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(label)