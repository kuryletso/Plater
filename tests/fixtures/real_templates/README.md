# Real-document fixtures

Six `.docx` templates authored by hand in Google Docs (exported to `.docx`) on
2026-09-03 as a manual test pass over the document engine, then kept here as
regression fixtures.

They exist because **python-docx writes far cleaner OOXML than a real editor
does**, so a synthetic fixture cannot reproduce the failures these files
found: one run per character, `{{` split across a colour change, smart quotes
in `sep=”\n”`, `<w:background>` as the first child of `<w:document>`, float
column widths, `headerReference type="first"` with no `<w:titlePg/>`.

Do not regenerate or "clean up" these files. Their messiness is the point.

| File | What it exercises |
| --- | --- |
| `empty.docx` | No placeholders at all; the degenerate ingest/render path. |
| `languages.docx` | Unsuffixed / primary / secondary placeholders, joined + grouped forms, `invoice_table` per language, `invl_*` cells per language. |
| `languages_invalid.docx` | A third language, invalid language suffixes, unregistered keys, and placeholders split by line break, paragraph break and page break. |
| `tables.docx` | `invoice_table` standalone, in a cell, in a multi-cell table and in a nested cell; `invl_*` rows standalone, in cells and nested; invoice-line cells beside plain text. |
| `formatting.docx` | Page size/margins/background, alignment, table alignment and width, merged cells, line spacing, indentation, embedded fonts, and a `{{ client_name }}` painted one letter per colour. |
| `layout.docx` | Landscape, image, header/footer (with `first` variants), multi-column sections, bullet and numbered lists. |

Load them through the `real_template` / `ingest_real` fixtures in
`tests/conftest.py` rather than by path.

The originals were also generated end to end through the GUI; the outputs of
that pass are *not* stored here, since the assertions describe what the output
should be rather than what it was.
