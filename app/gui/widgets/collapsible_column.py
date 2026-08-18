from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.draft_state import ColumnStatus


QWIDGETSIZE_MAX = 16777215      # Not present in current version of PySide6 so set manually

RAIL_WIDTH = 48
ANIMATION_MS = 120

class VerticalLabel(QWidget):
    """QLabel cannot rotate text; painting it ourselves is the trick."""

    def __init__(
            self,
            text: str,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._text = text
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)


    def sizeHint(self):
        return self.fontMetrics().size(0, self._text).transposed()


    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.translate(0, self.height())
        painter.rotate(-90)
        painter.drawText(
            0, 0, self.height(), self.width(),
            Qt.AlignmentFlag.AlignCenter, self._text,
        )


class CollapsibleColumn(QFrame):
    """One accordion column: full body when active, a thin rail when not."""

    activated = Signal()

    def __init__(
            self,
            title: str,
            content: QWidget,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._rail = self._build_rail(title)
        self._body = self._build_body(title, content)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self._rail)
        layout.addWidget(self._body)

        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.finished.connect(self._finish_animation)
        self._expanded = True

        self.set_expanded(False, animate=False)


    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if expanded == self._expanded and self._animation.state() == QPropertyAnimation.State.Stopped:
            return

        self._expanded = expanded
        self._animation.stop()

        if not animate or ANIMATION_MS == 0:
            self._body.setVisible(expanded)
            self._rail.setVisible(not expanded)
            if expanded:
                self.setMinimumWidth(0)
                self.setMaximumWidth(QWIDGETSIZE_MAX)
            else:
                self.setFixedWidth(RAIL_WIDTH)
            return

        self._rail.setVisible(False)
        self._body.setVisible(True)
        self.setMinimumWidth(0)

        parent = self.parentWidget()
        target = (parent.width() if parent else 1600) if expanded else RAIL_WIDTH

        self._animation.setStartValue(self.width())
        self._animation.setEndValue(target)
        self._animation.start()


    def mousePressEvent(self, event) -> None:
        """The whole rail is a target, not just the arrow button."""

        if not self._body.isVisible():
            self.activated.emit()
        super().mousePressEvent(event)


    def set_status(self, status: ColumnStatus) -> None:
        """Neutral while pristine. Red once the column has regresed."""

        self.setProperty("status", status.value)
        self.style().unpolish(self)
        self.style().polish(self)


    def _build_rail(self, title: str) -> QWidget:
        expand = QToolButton()
        expand.setArrowType(Qt.ArrowType.RightArrow)
        expand.setAutoRaise(True)
        expand.clicked.connect(self.activated)

        rail = QWidget()
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(2,4,2,4)
        layout.addWidget(expand, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(VerticalLabel(title), 1, Qt.AlignmentFlag.AlignHCenter)

        return rail


    def _build_body(self, title: str, content: QWidget) -> QWidget:
        header = QLabel(title)
        font = header.font()
        font.setBold(True)
        header.setFont(font)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(header)
        layout.addWidget(content, 1)

        return body


    def _finish_animation(self) -> None:
        if self._expanded:
            self.setMaximumWidth(QWIDGETSIZE_MAX)
        else:
            self._body.setVisible(False)
            self._rail.setVisible(True)
            self.setFixedWidth(RAIL_WIDTH)


class Accordion(QWidget):
    """Row of CollapsibleColumns exactly one is expanded at any moment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns: list[CollapsibleColumn] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0,0,0,0)


    def add_column(self, column: CollapsibleColumn) -> None:
        self._columns.append(column)
        self._layout.addWidget(column)
        column.activated.connect(lambda c=column: self.set_active(c))

        if len(self._columns) == 1:
            self.set_active(column, animate=False)


    def set_active(self, active: CollapsibleColumn, animate: bool = True) -> None:
        for column in self._columns:
            column.set_expanded(column is active, animate=animate)
            self._layout.setStretchFactor(column, 1 if column is active else 0)