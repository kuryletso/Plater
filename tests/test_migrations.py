"""The migrations build exactly the schema the models describe.

The suite's own databases come from Base.metadata.create_all(), so a model change
without a migration would pass every other test and fail at a user's startup.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# A fresh process: app.db.session fixes its database URL when first imported.
COMPARE = """
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.db.models
from app.db.base import Base
from app.db.session import DATABASE_URL, _alembic_config

command.upgrade(_alembic_config(), "head")
engine = create_engine(DATABASE_URL)
with engine.connect() as connection:
    print(compare_metadata(MigrationContext.configure(connection), Base.metadata))
engine.dispose()
"""


def test_the_migrations_build_the_schema_the_models_describe(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", COMPARE],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PLATER_DB": str(tmp_path / "plater.db")},
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", "models and migrations differ: write a migration"
