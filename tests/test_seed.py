"""Reference data seeding: the JSON files in app/db/seed_data, upserted on every launch."""

import json

import pytest
from sqlalchemy.orm import Session

from app.db import seed as seed_module
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry
from app.db.seed import SeedSpec, seed
from app.db.seed_registry import SEED_SPECS, expand_tax_id_system


def test_the_shipped_seed_files_seed_a_fresh_database():
    """Nothing else reads the real files, so data the database rejects, such as a
    string "TRUE" where a boolean belongs, passed the suite and stopped the app at
    startup. Foreign keys are on, as in production."""
    from sqlalchemy import create_engine, event, select

    from app.db.base import Base
    from app.db.connection import configure_sqlite

    engine = create_engine("sqlite://")
    event.listen(engine, "connect", configure_sqlite)

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed(session, SEED_SPECS)

        assert session.scalars(select(TaxIdSystemRegistry)).first() is not None


@pytest.fixture
def seed_tax_systems(session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr(seed_module, "SEED_DIR", tmp_path)

    def _seed(*rows: dict) -> None:
        path = tmp_path / "tax_id_systems.json"
        path.write_text(json.dumps(list(rows), ensure_ascii=False), encoding="utf-8")
        seed(session, (SeedSpec("tax_id_systems.json", expand_tax_id_system),))

    return _seed


def edrpou(**overrides) -> dict:
    return {
        "code": "ua_edrpou", "name": "EDRPOU", "name_UKR": "ЄДРПОУ",
        "system": True, "active": True,
    } | overrides


def test_seeding_labels_a_tax_system_already_there(session: Session, seed_tax_systems):
    """The migration adds the columns empty; the next launch's seeding fills them,
    and the names documents print stay as they were."""

    seed_tax_systems(edrpou(label_en="EDRPOU code", label_uk="Код ЄДРПОУ"))
    system = session.get(TaxIdSystemRegistry, "ua_edrpou")

    assert (system.label_en, system.label_uk) == ("EDRPOU code", "Код ЄДРПОУ")
    assert {code: row.name for code, row in system.localizations.items()} == {
        "ENG": "EDRPOU", "UKR": "ЄДРПОУ",
    }


def test_a_blank_label_is_stored_as_none(session: Session, seed_tax_systems):
    """So the interface falls back to the English label instead of showing nothing."""

    seed_tax_systems(edrpou(label_en="EDRPOU code", label_uk=""))

    assert session.get(TaxIdSystemRegistry, "ua_edrpou").label_uk is None


def test_a_tax_system_without_labels_still_seeds(session: Session, seed_tax_systems):
    seed_tax_systems(edrpou(code="ua_new"))
    system = session.get(TaxIdSystemRegistry, "ua_new")

    assert (system.label_en, system.label_uk) == (None, None)
