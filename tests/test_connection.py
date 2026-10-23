"""The app engine's per-connection setup (app/db/connection.py).

conftest points PLATER_DB at a temporary directory, so connecting here never touches
the developer's own database.
"""

from app.db.session import engine


def test_the_app_s_connections_have_foreign_keys_on():
    """SQLite ignores a pragma it does not know, so a misspelt one switched them off
    without a word."""

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_the_app_s_connections_fold_cyrillic_case():
    """SQLite's own lower() folds ASCII only; search depends on Python's."""

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT lower('ТОВ Ґудзик')").scalar() == "тов ґудзик"
