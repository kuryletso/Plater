from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Plater"

def user_data_dir() -> Path:

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")

    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"

    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")

    return Path(base) / APP_NAME


def database_path() -> Path:

    override = os.environ.get("PLATER_DB")
    return Path(override) if override else user_data_dir() / "plater.db"


def assets_dir() -> Path:

    return user_data_dir() / "assets"


def settings_path() -> Path:
    override = os.environ.get("PLATER_SETTINGS")
    return Path(override) if override else user_data_dir() / "plater.ini"


PROJECT_ROOT = Path(__file__).resolve().parent.parent