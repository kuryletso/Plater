from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QListWidget, QTextBrowser

from app.core.errors import Severity


class PreviewPanel(QFrame):
    """Shows what render would say about this draft, shown before 
    a sequence number is consumed.
    
    Becomes the live HTML preview when the html emitter lands.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        # self.issues_list = QListWidget()
        self.issues_view = QTextBrowser()
        self.issues_view.setOpenExternalLinks(False)

        footnote = QLabel("Visual preview will appear here in a future version.")
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.issues_view, 1)
        layout.addWidget(footnote)

        self.show_notice("Finish document setup to preview")


    def show_notice(self, text: str) -> None:
        self._set_status(text, role="")
        self.issues_view.clear()


    def show_result(self, number: str, diagnostics) -> None:
        rows = []
        for item in diagnostics.items:
            color = "#c0392b" if item.severity == Severity.ERROR else "#8a6d00"
            rows.append(
                f'<p style="margin:0 0 8px 0; color:{color}">{escape(item.message)}</p>'
            )

        self.issues_view.setHtml("".join(rows))
        
        warnings = len(diagnostics.warnings)

        if diagnostics.has_errors:
            self._set_status(
                f"{number} cannot be generated until these issues are fixed.",
                role="error",
            )
        elif warnings:
            self._set_status(
                f"{number} will generate, with {warnings} warning(s).",
                role="warning",
            )
        else:
            self._set_status(
                f"{number} is ready to generate. No issues found.",
                role="",
            )


    def _set_status(self, text: str, *, role:str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("role", role)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)