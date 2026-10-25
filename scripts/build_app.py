"""Build Plater for this this platform: python scripts/build_app.py

1. Compiles the forms and translations (scripts/build_ui.py);
2. Draws build/plater.ico from app/gui/icons/plater.svg;
3. Runs PyInstaller with packaging/plater.spec into dist/Plater;
4. Pyts the licenses beside the app;
5. on Windows, compiles dist/Plater-Setup.exe with Inno Setup, if it's installed.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILD = PROJECT_ROOT / "build"
DIST = PROJECT_ROOT / "dist"
PACKAGING = PROJECT_ROOT / "packaging"
ICON = PROJECT_ROOT / "app" / "gui" / "icons" / "plater.svg"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

ISCC_PLACES = (
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
)


def run(*command: str | Path) -> None:
    print("$", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True, cwd=PROJECT_ROOT)


def version() -> str:
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def render_png(svg: Path, size: int) -> bytes:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _app = QGuiApplication.instance() or QGuiApplication([])
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(svg)).render(painter)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")       # type: ignore
    return bytes(data.data())


def write_ico(target: Path, svg: Path, sizes: tuple[int, ...]) -> None:
    """An .ico of PNG images, one per size, each drawn from the SVG to keep all sharp."""

    images = [(size, render_png(svg, size)) for size in sizes]
    offset = 6 + 16 * len(images)
    header = struct.pack("<HHH", 0, 1, len(images))
    entries = b""
    for size, png in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)

    target.write_bytes(header + entries + b"".join(png for _, png in images))


def copy_licenses(app_dir: Path) -> None:
    """Plater's own license and the LGPL."""

    shutil.copy(PROJECT_ROOT / "LICENSE", app_dir / "LICENSE.txt")
    licenses = PACKAGING / "licenses"
    if licenses.is_dir():
        shutil.copytree(licenses, app_dir / "licenses", dirs_exist_ok=True)
    else:
        print(f"warning: {licenses.relative_to(PROJECT_ROOT)} is missing; the build has no third-party licenses")


def iscc() -> Path | None:
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    return next((place for place in ISCC_PLACES if place.is_file()), None)


def main() -> int:
    run(sys.executable, "scripts/build_ui.py")

    BUILD.mkdir(exist_ok=True)
    write_ico(BUILD / "plater.ico", ICON, ICON_SIZES)

    run(
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
        "--workpath", BUILD / "pyinstaller", PACKAGING / "plater.spec",
    )
    copy_licenses(DIST / "Plater")

    if sys.platform == "win32":
        compiler = iscc()
        if compiler is None:
            print("Inno Setup not found: dist/Plater is built, the installer is not")
        else:
            run(compiler, f"/DAppVersion={version()}", PACKAGING / "windows" / "plater.iss")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())