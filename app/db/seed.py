from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

SEED_DIR = Path(__file__).parent / "seed_data"


Rows = list[dict]
Batch = tuple[tuple[type, Rows], ...]


@dataclass(frozen=True)
class SeedSpec:
    filename: str
    expand: Callable[[Rows], Batch]


def _upsert(
        session: Session,
        model,
        rows: list[dict],
) -> None:
    
    if not rows:
        return
    
    pk = [ c.name for c in model.__table__.primary_key ]
    stmt = insert(model).values(rows)

    updatable = { c: stmt.excluded[c] for c in rows[0] if c not in pk }
    if updatable:
        stmt = stmt.on_conflict_do_update(index_elements=pk, set_=updatable)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=pk)

    session.execute(stmt)


def seed(
        session: Session,
        specs: tuple[SeedSpec, ...],
) -> None:

    for spec in specs:
        raw = json.loads((SEED_DIR / spec.filename).read_text(encoding="UTF-8"))
        for model, rows in spec.expand(raw):
            _upsert(session, model, rows)

    session.commit()


def _language_row(raw: dict) -> dict:
    return {
        "code": raw["ISO 639-3"].upper(),
        "code_alpha_2": raw["ISO 639-1"],
        "label_en": raw["ISO language name"],
        "label_uk": raw["Ukrainian"],
    }