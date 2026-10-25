"""The app's own version, as the session log and the About box show it."""

import tomllib
from importlib import metadata

from app.paths import PROJECT_ROOT


def app_version() -> str:
    """pyproject.toml is the version's one home, and a build bundles it beside the app. 
    Plater runs from source, so there is no package metadata unless it was installed.
    """

    try:
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as file:
            return tomllib.load(file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass

    try:
        return metadata.version("Plater")
    except metadata.PackageNotFoundError:
        return "unknown"