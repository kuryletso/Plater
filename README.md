# Plater

Generate invoices and similar business documents from your own Word templates.

Design a `.docx` template in Word or Google Docs, put placeholders where the data goes, and
import it. Plater keeps a local library of organizations, bank accounts,
representatives, numbering sequences and invoice lines, and fills the template to
produce a correctly numbered document — in one language or two.

Everything runs locally: a desktop app (Qt) over a SQLite database in your user
profile. Nothing is sent anywhere.

## Status

Functionally complete for a first release and in active use, but still
**pre-release**: there are no installers yet, so it runs from source, and the
interface is English-only until the translation pass lands.

## Features

- **Your own templates.** Import any `.docx`. Templates keep a version history with
  option to restore previous version. Four built-in templates ship with the app.
- **Bilingual documents.** Each template has a primary and an optional secondary
  language, and any placeholder can be pinned to either.
- **Parties.** Organizations with localized names and addresses, tax IDs, bank
  accounts, and representatives shared between organizations.
- **Numbering.** Per-organization sequences for each document type, with a prefix
  and zero-padding. A number is consumed only when a document is actually
  generated.
- **Invoice lines.** Typed straight into a grid, with autocomplete from lines
  you have used before, units, quantities, prices and tax rates.
- **Preview before you generate.** Everything the renderer would complain about
  is listed while you fill in the document, before a number is assigned.
- **Money done properly.** Amounts are formatted per currency and language, lines
  are rounded before they are summed so the printed total reconciles, and the
  total can be spelled out in words.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13, which uv installs for
you if needed.

```bash
uv sync
uv run python scripts/build_ui.py
uv run python -m app.gui.main
```

`build_ui.py` compiles the Qt Designer forms in `app/gui/designer/`. The compiled
files are not committed, so run it after cloning and whenever a `.ui` file changes.

The database is created and migrated on first launch, together with the built-in
templates and reference data (languages, countries, currencies, tax systems and
units). It lives in your user data directory:

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Plater\` |
| macOS | `~/Library/Application Support/Plater/` |
| Linux | `$XDG_DATA_HOME/Plater/` or `~/.local/share/Plater/` |

`plater.db` holds your data and `plater.ini` your interface preferences. Set
`PLATER_DB` or `PLATER_SETTINGS` to use different files.

## Writing templates

A placeholder is a key in double braces. Plater replaces it with the value and
keeps the formatting of the text around it.

| Form | Example | Result |
| --- | --- | --- |
| Simple | `{{ client_name }}` | The value, in the template's primary language |
| Language | `{{ client_name.UKR }}` | The value in a specific language |
| Joined | `{{ prefix, id, sep="" }}` | Parts joined by `sep`; empty parts are skipped |
| Grouped | `{{ ((client_bank_name, client_iban), (client_swift)), sep="\n" }}` | Members joined by spaces, groups by `sep`; a group with any empty member is dropped |
| Invoice table | `{{ invoice_table }}` | A complete table of the invoice lines, with subtotal, tax and total |
| Invoice line | `{{ invl_desc }}` in a table row | The row repeats once per invoice line |

The `sep` default is `", "`, and it understands `\n` (line break) and `\t` (tab).
Languages use three-letter codes such as `ENG` and `UKR`.
String literals can be used inside placeholders, e.g. `{{ (("Contractor repesentative: ", provider_rep_name)), sep="\n" }}`

**Available keys** — the full list, with descriptions, is in
[`app/db/seed_data/placeholder.json`](app/db/seed_data/placeholder.json):

- **Document:** `date`, `prefix`, `id`, `curr`, `subtotal`, `total_tax`, `total`,
  `total_text` (the total in words)
- **Parties** — each exists as `provider_*` and `client_*`: `name`, `type`,
  `address`, `country`, `tax_id`, `tax_sys`, `phone`, `email`, `iban`, `swift`,
  `bank_name`, `bank_info`, `rep_name`, `rep_title`
- **Invoice lines:** `invoice_table`, or for a row of your own design `invl_n`,
  `invl_desc`, `invl_unit`, `invl_qnty`, `invl_price`, `invl_tax`, `invl_total`

**Good to know**

- `{{ invoice_table }}` must be the only thing in its paragraph. Placed anywhere
  inside a table, it replaces that whole table and takes on its width and borders.
- A placeholder can span a soft line break (Shift+Enter), which makes long grouped
  placeholders easier to write, but not a paragraph break (Enter).
- Put at most one invoice-line placeholder in each table cell. Outside a table
  row they have nothing to repeat against, so they render empty.
- A misspelled key or an unknown language is kept as plain text and reported as a
  warning at import, so a typo never blocks a template.

### What a template can use

Preserved: bold, italic, underline, fonts, sizes and colors; paragraph alignment,
indentation, spacing and line spacing; page size, orientation and margins; multiple
sections; headers and footers, including first-page and even-page variants; tables
with column widths, borders, shading, horizontally merged cells and alignment;
images, including in headers and footers; page numbers and page counts; page breaks
and tabs.

Hyperlinks are kept as plain text by design, since generated documents are meant
for print. Other Word fields, such as dates or cross-references, keep the text they
last showed, and are reported at import.

Not yet supported, and silently dropped: bulleted and numbered lists,
strikethrough, small caps, superscript and subscript, highlighting, vertically
merged cells, text columns, page backgrounds, horizontal rules and embedded fonts.
The text and placeholders around them still render.

When a new version of Plater reads templates better, the built-in templates are
updated on the next launch and you are offered a one-click rebuild of your own.
Nothing about a template changes except how its original file is read.

## Development

```bash
uv run pytest
```

The suite includes real Word and Google Docs templates in
`tests/fixtures/real_templates/`, because python-docx writes far tidier documents
than real editors do, and synthetic fixtures miss most real-world bugs.

- **Forms:** edit the `.ui` files in `app/gui/designer/` with
  `uv run pyside6-designer`, then rerun `scripts/build_ui.py`.
- **Manual checks:** `scripts/render_invoice.py` renders a full invoice from a
  throwaway database, and `scripts/render_raw.py` renders a template with its
  placeholders left in place. Output goes to `scripts/output/`.
- **Lint:** `scripts/review_changes.sh` runs ruff over the Python files you have
  changed, outside `tests/`.
- **Migrations:** Alembic, applied automatically at startup.

The document engine works in two stages. At **import**, a `.docx` is parsed,
normalized and turned into a *blueprint*, which is stored with the original file.
At **generation**, the blueprint is validated against the data, resolved and
written out as a new `.docx`. A blueprint records how a given engine read the file,
so when the engine changes, `ENGINE_VERSION` is bumped and stored blueprints are
rebuilt from their original files.

```text
app/
  document_engine/   .docx parsing, blueprints and rendering
  services/          repositories, invoice assembly and generation
  db/                models, migrations and seed data
  gui/               the Qt interface
tests/
scripts/
```

## License

Copyright (C) 2026 Oleksandr Kurylets

Plater is free software: you can redistribute it and/or modify it under the terms
of the GNU Affero General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

Plater is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along
with Plater, in [LICENSE](LICENSE). If not, see <https://www.gnu.org/licenses/>.

In plain terms: anyone may use, study, change and share Plater, including for
paid work such as invoicing clients. Anyone who distributes it, or runs a
modified version as a network service, must make the complete source available
under the same license and keep this copyright notice.

Plater uses [PySide6](https://doc.qt.io/qtforpython/) (Qt for Python) under the
LGPL-3.0 and [num2words](https://github.com/savoirfairelinux/num2words) under the
LGPL-2.1, both unmodified and as separate libraries. Its other dependencies are
under MIT and BSD licenses.
