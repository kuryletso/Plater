# Golden blueprints

Blueprints as older engines wrote them, loaded by
`tests/test_blueprint_compat.py` on every run.

A template's blueprint is stored as JSON and validated against today's models
each time it is loaded, and the models forbid unknown fields. So adding a field
without a default, or renaming or removing one, silently breaks every template a
user has already imported. That happened once — `title_page`, 2026-09-10 — and
these files turn it into a failing test instead.

| Files | Written by |
| --- | --- |
| `engine_0_*.json` | Real stored blueprints lifted from an install's database, ingested before engine stamping existed (2026-09-03). |
| `engine_2_*.json` | Engine 2, dumped from the real-template fixtures on 2026-09-10. |
| `engine_3_*.json` | Engine 3, dumped from the refreshed real-template fixtures on 2026-09-23, just before batch A. |
| `engine_4_*.json` | Engine 4, dumped on 2026-09-25 when batch A closed: header/footer images, page-number fields, text inside hyperlinks and content controls. |

**Never regenerate these files.** Their age is the point. When `ENGINE_VERSION`
is bumped, add a new generation beside them rather than replacing them.

If one of them stops loading, the fix is almost never to edit the file: give the
new field a default, or bump `ENGINE_VERSION` so stored templates get rebuilt from
their source.
