from __future__ import annotations

from alembic import command
from alembic.config import Config

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.paths import database_path, user_data_dir, PROJECT_ROOT

from app.services.settings import TemplateDefaultService

DATABASE_URL = f"sqlite:///{database_path().as_posix()}"

engine = create_engine(
    DATABASE_URL,
    # echo=True     # uncomment for debugging
)

@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)


def _alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def init_db() -> None:
    from app.db.seed import seed
    from app.db.seed_registry import SEED_SPECS
    from app.services.template.defaults import seed_default_templates

    user_data_dir().mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(), "head")      # migrate: fresh, updated or shared DB

    with SessionLocal() as session:
        seed(session, SEED_SPECS)
        TemplateDefaultService(session).ensure()
        seed_default_templates(session)