"""Raw-render templates with placeholders left as ``{{ key }}``.

No invoice data is involved — KEYS mode needs no RenderContext at all — so this is
the quickest way to see what a template asks for and how it lays out.

    uv run python scripts/render_raw.py
    uv run python scripts/render_raw.py --template default_ukr_invoice
    uv run python scripts/render_raw.py --file path/to/your.docx --primary UKR

Outputs land in scripts/output/ as <code>.raw.docx.
"""

from __future__ import annotations

import argparse

import _scenario as scenario                                       # noqa: E402  (must precede app.db)
from _scenario import OUTPUT_DIR, banner, print_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="raw-render only this seeded template code")
    parser.add_argument("--file", help="ingest and raw-render this .docx instead")
    parser.add_argument("--primary", default="ENG", help="primary language for --file")
    parser.add_argument("--secondary", default="UKR", help="secondary language for --file")
    parser.add_argument("--type", default="invoice", help="document type code for --file")
    parser.add_argument("--verbose", action="store_true", help="dump the full document")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    banner("1. Initialise database (migrate + seed reference data + seed templates)")
    scenario.initialise()

    from sqlalchemy import select

    from app.assets.provider import DbAssetProvider
    from app.db.models.core.template import Template
    from app.db.session import SessionLocal
    from app.document_engine.blueprint.models.template import TemplateConfig
    from app.document_engine.orchestration.pipeline import TemplateRenderingPipeline
    from app.services.template.db_input_provider import DbTemplateInputProvider
    from app.services.template.import_service import TemplateImportService
    from app.services.template.repository import TemplateRepository

    banner("2. Choose the template(s)")
    with SessionLocal() as session:
        if args.file:
            session.add(scenario.default_template_config(
                primary=args.primary, secondary=args.secondary, document_type=args.type,
            ))
            session.commit()

            service = TemplateImportService(session, DbTemplateInputProvider(
                session,
                config=TemplateConfig(
                    primary_language=args.primary,
                    secondary_language=args.secondary or None,
                    type=args.type,
                    name="Manual test template",
                    description="",
                    append_currency=True,
                ),
            ))
            result = service.ingest(args.file)
            for warning in result.diagnostics.warnings:
                print(f"   WARNING {warning.code}: {warning.message}")
                if warning.context:
                    print(f"           {warning.context}")
            template_ids = [service.commit(result)]
            print(f"   ingested {args.file} -> template {template_ids[0]}")
        else:
            query = select(Template).order_by(Template.code)
            if args.template:
                query = query.where(Template.code == args.template)
            template_ids = [t.id for t in session.scalars(query).all()]
            print(f"   seeded templates: {len(template_ids)}")

    if not template_ids:
        print("   nothing to render — check --template")
        return 1

    failures = 0
    for template_id in template_ids:
        with SessionLocal() as session:
            template = session.get(Template, template_id)
            blueprint = TemplateRepository(session).get_blueprint(template_id)
            label = template.code or template.name

            banner(f"3. {label} — raw render")

            render = TemplateRenderingPipeline(DbAssetProvider(session)).render_raw(
                blueprint,
            )
            for item in render.diagnostics.items:
                print(f"   [{item.severity}] {item.code}: {item.message}")

            if render.docx is None:
                print("   RENDER FAILED")
                failures += 1
                continue

            out = OUTPUT_DIR / f"{label}.raw.docx"
            out.write_bytes(render.docx)

            text = scenario.describe_docx(out)
            declared = set(blueprint.placeholders)
            visible = {key for key in declared if f"{{{{ {key} }}}}" in text}
            missing = sorted(declared - visible)

            print(f"   wrote {len(render.docx):,} bytes -> {out}")
            print(f"   placeholders: {len(visible)}/{len(declared)} visible")
            if missing:
                print(f"   not surfaced: {missing}")
                print("      (keys inside nested tables are not reported by python-docx)")

            if args.verbose:
                print_document(out)

    banner("done")
    print(f"   output: {OUTPUT_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
