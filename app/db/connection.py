"""Per-connection SQLite setup. Shared by the app's engine and tests."""

from typing import Any

def configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    """Foreign keys are enabled explicitly for every connection.
    
    Python's _lower() replaces SQLite's lower() since the latter folds ASCII only, and 
    skips Cyrillic.
    """

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

    dbapi_connection.create_function("lower", 1, _lower, deterministic=True)


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value