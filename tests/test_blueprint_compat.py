"""Stored blueprints written by older engines must keep loading.

`load_blueprint()` validates the stored JSON against today's models on every
load, and `BlueprintBase` is `extra="forbid"`. So a field added without a
default — or renamed, or removed — makes every template imported before the
change unloadable. That happened once (`title_page`, 2026-09-10); these files
make it fail the suite instead of the user's templates.

`engine_0_*` are real stored blueprints lifted from an install's database,
written before engine stamping existed. `engine_2_*` were dumped from engine 2.
Never regenerate either: their age is the point. Add a new generation instead
whenever `ENGINE_VERSION` is bumped.
"""

import json
from pathlib import Path

import pytest

from app.document_engine.blueprint.serialize import load_blueprint


GOLDEN = Path(__file__).parent / "fixtures" / "blueprints"


def golden_blueprints() -> list[Path]:
    return sorted(GOLDEN.glob("*.json"))


def test_the_golden_blueprints_are_present():
    """Parametrizing over an empty glob would pass the guard vacuously."""

    assert {path.stem.split("_")[1] for path in golden_blueprints()} >= {"0", "2"}


@pytest.mark.parametrize("path", golden_blueprints(), ids=lambda path: path.stem)
def test_a_blueprint_written_by_an_older_engine_still_loads(path: Path):
    stored = json.loads(path.read_text(encoding="utf-8"))

    blueprint = load_blueprint(stored["sections"], stored["placeholders"], stored["config"])

    assert blueprint.sections
