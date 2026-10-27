# Plater

Generate invoices and similar business documents from your own Word templates.

Design a `.docx` template in Word or Google Docs, put placeholders where the data goes, and
import it. Plater keeps a local library of organizations, bank accounts,
representatives, numbering sequences and invoice lines, and fills the template to
produce a correctly numbered document — in one language or two.

Everything runs locally: a desktop app (Qt) over a SQLite database in your user
profile. Nothing is sent anywhere.

## Status

Version 1.0, in active use. Each [release](https://github.com/kuryletso/Plater/releases/latest) 
comes with a Windows installer; a macOS build is planned. On other platforms Plater runs from source.
The interface is in English and Ukrainian (*Settings -> Preferences*).

## Features

- **Your own templates.** Import any `.docx`. Templates keep a version history with
  option to restore previous version. Four built-in templates ship with the app.
- **Bilingual documents.** Each template has a primary and an optional secondary
  language, and any placeholder can be pinned to either.
- **English and Ukrainian interface.** Menus, dialogs, import warnings, the preview and error messages. 
  Changing language takes effect on the next start.
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

## Install (Windows)

1. Download [Plater-Setup.exe](https://github.com/kuryletso/Plater/releases/latest/download/Plater-Setup.exe)
  from the latest release.
2. Run it. It installs for your Windows user only, without admin rights, into `%LOCALAPPDATA%\Programs\Plater` by default, and adds Plater to the Start menu.

The installer is not code-signed yet, so Windows may say *"Windows protected your PC"*. Choose **More info**, then **Run anyway**.

To update, run a newer installer over existing installation.
Uninstall as any other program (*Settings -> Apps*). Uninstalling does not remove your data.

## Your data

The database is created on first launch, together with the built-in templates and reference data (languages, countries, currencies, tax systems and units), and updated automatically by newer versions.
It lives in your user data folder:

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Plater\` |
| macOS | `~/Library/Application Support/Plater/` |
| Linux | `$XDG_DATA_HOME/Plater/` or `~/.local/share/Plater/` |

`plater.db` holds your data and `plater.ini` is your interface preferences. Back up `plater.db` to keep your data safe. Keep it on a local disk: SQLite databases can be damaged on network drives.

*Help -> Open log folder* shows `plater.log`, the record of the current session. The previous one is `plater.prev.log`. Attach it when you report a problem. It does not carry user data.

## Run from source

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13, which uv installs for
you if needed.

```bash
uv sync
uv run python scripts/build_ui.py
uv run python -m app.gui.main
```

`build_ui.py` compiles the Qt Designer forms in `app/gui/designer/` and the translations 
in `app/gui/translations/`. Neither is committed, so run it after cloning and whenever a `.ui` or `.ts` file changes.

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

Preserved: bold, italic, underline, strikethrough, small caps, superscript and
subscript, highlighting, fonts, sizes and colors; embedded fonts; paragraph
alignment, indentation (hanging indents included), spacing, line spacing and
borders; bulleted and numbered lists; horizontal lines; page size, orientation,
margins and page color; multiple sections and text columns; headers and footers,
including first-page and even-page variants; tables with column widths, borders,
shading, merged cells and alignment; images, including in headers and footers;
page numbers and page counts; page and column breaks, and tabs.

Some of these come out slightly different from the original:

- A horizontal line is drawn as a border under its paragraph, so it may look a
  little different, and a line narrower than the page comes out full width.
- Images are always placed in line with the text. Text wrapping and floating
  positions are not kept.
- A merged cell that starts in an invoice-line row is split back into separate
  cells, since that row repeats once per line. The import says when it does this.
- Word prints a page color only when its *Print background colors and images*
  option is on.

Hyperlinks are kept as plain text by design, since generated documents are meant
for print. Other Word fields, such as dates or cross-references, keep the text they
last showed, and are reported at import.

Not supported, and silently dropped: text boxes and shapes, footnotes and
endnotes, comments. The text and placeholders around them still render.

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
- **Translations:** after changing interface text, run 
  `scripts/update_translations.py`, translate what is new with
  `uv run pyside6-linguist app/gui/translations/plater_uk.ts`, then rerun
  `scripts/build_ui.py`. `plater_en.ts` only holds English plural forms. The test suite fails 
  while any text lacks a translation. 
- **Manual checks:** `scripts/render_invoice.py` renders a full invoice from a
  throwaway database, and `scripts/render_raw.py` renders a template with its
  placeholders left in place. Output goes to `scripts/output/`.
- **Lint:** `scripts/review_changes.sh` runs ruff over the Python files you have
  changed, outside `tests/`.
- **Migrations:** Alembic, applied automatically at startup.
- **Builds and releases:** `scripts/build_app.py` builds the app into `dist/Plater/` and, 
  on Windows with [Inno Setup](https://jrsoftware.org/isinfo.php) installed, `dist/Plater-Setup.exe`.
  `scripts/smoke_app.py` then starts the build and checks its log. Pushing a tag `vX.Y.Z` that matches `pyproject.toml` makes GitHub Actions test, build, smoke-test and publish a release.

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

### Conventions

- **Keys.** Everything a user creates (organizations, tax IDs, bank accounts,
  representatives, sequences, templates and their versions, invoice lines) has an
  integer `id`. Reference and registry data (languages, countries, currencies,
  document types, units, tax systems, placeholders) is keyed by its code, and
  stored files by their SHA-256. Keep new tables to this. The session log records
  ids and codes rather than names, so a new entity with a UUID or other key would
  show up in the log without one.
- **Session log.** `plater.log` sits beside the database, with the previous
  session kept as `plater.prev.log`; set `PLATER_LOG` to move it. Actions are
  logged at the service boundary with `@logged` from `app/core/log.py`. Log ids,
  counts and diagnostic codes. DO NOT log user-provided data (names, addresses, descriptions etc.), including user_message from diagnostics service.
- **Empty values** are `None`, never `""` (empty string).
- **Text for users.** In the GUI `self.tr("...")` always goes with a literal;
  values go in `{named}` fields filled with `.format()`, never in an f-string, and never call `tr()` 
  inside f-string. A count uses `%n` through `self.tr()` only. `QCoreApplication.translate()` loses its plural forms unless the count is a literal number. Outside the GUI (services and the engine), a user message or diagnostic is a template marked with `QT_TRANSLATE_NOOP("messages", "...")`, filled from the error's or diagnostic's context, so the user's data is only ever a value.

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

The installed app lists every bundled component and its license in
`licenses\THIRD-PARTY.txt`.