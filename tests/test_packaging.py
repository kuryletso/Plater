"""What a packaged Plater relies on: its version, and a database file of its own."""

import sqlite3
import stat
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_the_version_comes_from_pyproject():
    from app.core.version import app_version

    with open(PROJECT_ROOT / "pyproject.toml", "rb") as file:
        assert app_version() == tomllib.load(file)["project"]["version"]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no owner-only mode bits; profile ACLs do that")
def test_a_new_database_is_readable_by_its_owner_only(tmp_path):
    from app.db.session import create_database_file

    path = tmp_path / "plater.db"
    create_database_file(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_sqlite_takes_the_empty_file_as_a_new_database(tmp_path):
    from app.db.session import create_database_file

    path = tmp_path / "new" / "plater.db"
    create_database_file(path)

    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE t (x)")
        connection.execute("INSERT INTO t VALUES (1)")
        assert connection.execute("SELECT x FROM t").fetchall() == [(1,)]


def test_an_existing_database_is_left_alone(tmp_path):
    from app.db.session import create_database_file

    path = tmp_path / "plater.db"
    path.write_bytes(b"not empty")
    create_database_file(path)

    assert path.read_bytes() == b"not empty"
