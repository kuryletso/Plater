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


CLEAR = """
from alembic import command
from sqlalchemy import create_engine, text
from app.db.session import DATABASE_URL, _alembic_config

config = _alembic_config()
command.upgrade(config, "2b350576ebe5")         # before saved lines became unique

engine = create_engine(DATABASE_URL)
with engine.begin() as connection:
    for line_id in (1, 2):                      # the duplicates the old write-back made
        connection.execute(text(
            "INSERT INTO invoice_lines (id, quantity, measurement_unit_code, unit_price, "
            "tax_rate, use_count, last_used_at) "
            "VALUES (:id, 1, 'hour', 1, 0, 1, CURRENT_TIMESTAMP)"
        ), {"id": line_id})
        connection.execute(text(
            "INSERT INTO invoice_line_localizations (invoice_line_id, language_code, description) "
            "VALUES (:id, 'ENG', 'Design work')"
        ), {"id": line_id})
engine.dispose()

command.upgrade(config, "head")

engine = create_engine(DATABASE_URL)
with engine.connect() as connection:
    print(connection.execute(text(
        "SELECT (SELECT count(*) FROM invoice_lines), "
        "(SELECT count(*) FROM invoice_line_localizations)"
    )).one())
engine.dispose()
"""


def test_upgrading_clears_the_duplicate_saved_lines(tmp_path):
    """The new key column is required and unique, so the old rows could not stay."""
    result = subprocess.run(
        [sys.executable, "-c", CLEAR],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PLATER_DB": str(tmp_path / "plater.db")},
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "(0, 0)"
