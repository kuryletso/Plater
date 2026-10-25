"""Tool-button icons: Plater's own SVGs, drawn in the palette's colors."""

from pathlib import Path

import pytest

ICONS_DIR = Path(__file__).resolve().parent.parent / "app" / "gui" / "icons"


def names() -> list[str]:
    return sorted(path.stem for path in ICONS_DIR.glob("*.svg"))


def test_the_icon_set_is_not_accidentally_empty():
    assert {"plus", "minus", "pencil", "trash", "close", "up", "down", "plater"} <= set(names())


@pytest.mark.parametrize("name", names() or ["none"])
def test_every_icon_draws_something(qt_app, name):
    from PySide6.QtCore import QSize

    from app.gui.icons import icon

    image = icon(name).pixmap(QSize(24, 24)).toImage()
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(image.width()) for y in range(image.height())
    ), "an empty or unreadable SVG draws nothing"


def test_a_disabled_icon_is_drawn_in_the_disabled_color(qt_app):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    from app.gui.icons import icon

    pencil = icon("pencil")
    normal = pencil.pixmap(QSize(24, 24), QIcon.Mode.Normal).toImage()
    disabled = pencil.pixmap(QSize(24, 24), QIcon.Mode.Disabled).toImage()

    assert normal != disabled
