"""Line icons for the tool buttons, drawn from Plater's own SVGs in the palette's button-text color."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS_DIR = Path(__file__).resolve().parent / "icons"

# drawn in multiple sizes so Qt picks a sharp one for any screen scale
SIZES = (16, 20, 24, 32, 48, 64)

def icon(name: str) -> QIcon:
    """`name` is a file in app/gui/icons, without .svg.
    
    Disabled buttons get the palette's disabled color.
    """

    svg = (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")
    palette = QGuiApplication.palette()

    result = QIcon()
    for mode, group in (
        (QIcon.Mode.Normal, QPalette.ColorGroup.Active),
        (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled),
    ):
        color = palette.color(group, QPalette.ColorRole.ButtonText).name()
        renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode("utf-8")))
        for size in SIZES:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            result.addPixmap(pixmap, mode)

    return result