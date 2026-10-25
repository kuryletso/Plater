# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Plater: one folder, no console window.
# Build through scripts/build_app.py, which first compiles the translations and draws
# the build/plater.ico this file expects.


from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build"

datas = [
    (str(ROOT / "pyproject.toml"), "."),       # app_version()
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / "alembic" / "env.py"), "alembic"),
    (str(ROOT / "alembic" / "script.py.mako"), "alembic"),
    (str(ROOT / "alembic" / "versions" / "*.py"), "alembic/versions"),
    (str(ROOT / "app" / "db" / "seed_data"), "app/db/seed_data"),
    (str(ROOT / "app" / "gui" / "icons" / "*.svg"), "app/gui/icons"),
    (str(ROOT / "app" / "gui" / "translations" / "*.qm"), "app/gui/translations"),
]

for distribution in ("alembic", "babel", "lxml", "num2words", "pillow", "pydantic", "pyside6-essentials", "sqlalchemy"):
    datas += copy_metadata(distribution, recursive=True)


a = Analysis(
    [str(ROOT / "app" / "gui" / "main.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["logging.config", "app.db.models"],
    excludes=["tkinter"],
    # the LGPL license lets a user swap in their own build of these, so they stay plain files bside the binaries
    module_collection_mode={"PySide6": "py", "shiboken6": "py", "num2words": "py"},
)

# only Ukrainian stays from Qt's own translations (~200 files) 
a.datas = [
    entry for entry in a.datas
    if Path(entry[0]).parts[:2] != ("PySide6", "translations") or Path(entry[0]).name == "qtbase_uk.qm"
]

# remove software OpenGL, Qt Widget app never loads it
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name != "opengl32sw.dll"]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Plater",
    console=False,
    icon=str(BUILD / "plater.ico"),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Plater", upx=False)