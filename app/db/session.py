from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.paths import database_path, user_data_dir, PROJECT_ROOT
from app.services.settings import TemplateDefaultService
from app.db.connection import configure_sqlite

DATABASE_URL = f"sqlite:///{database_path().as_posix()}"

engine = create_engine(
    DATABASE_URL,
    # echo=True     # uncomment for debugging
)

event.listen(engine, "connect", configure_sqlite)

SessionLocal = sessionmaker(bind=engine)


def _alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    cfg.attributes["configure_logger"] = False      # keeps the app's own session log (see alembic/env.py)
    return cfg


def init_db() -> None:
    from app.db.seed import seed
    from app.db.seed_registry import SEED_SPECS
    from app.services.template.defaults import seed_default_templates

    user_data_dir().mkdir(parents=True, exist_ok=True)
    create_database_file(database_path())
    command.upgrade(_alembic_config(), "head")      # migrate: fresh, updated or shared DB

    with SessionLocal() as session:
        seed(session, SEED_SPECS)
        TemplateDefaultService(session).ensure()
        seed_default_templates(session)


def create_database_file(path: Path) -> None:
    """An mepty file SQLite takes as a new database, only readable by its owner where file modes apply (macOS). 
    SQLite gives its journal the same mode. On Windows the profile's permissions do that job. An existing file 
    is left as is.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch(mode=0o600)