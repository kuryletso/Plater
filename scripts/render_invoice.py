"""Render a real invoice end to end, against a freshly migrated and seeded database.

Drives every stage: migrate -> seed -> ingest -> persist -> load -> assemble -> map
-> render -> re-open and verify.

    uv run python scripts/render_invoice.py
    uv run python scripts/render_invoice.py --template default_ukr_invoice
    uv run python scripts/render_invoice.py --file path/to/your.docx --primary UKR

Outputs land in scripts/output/.
"""

from __future__ import annotations

import argparse
from datetime import date

import _scenario as scenario                                       # noqa: E402  (must precede app.db)
from _scenario import OUTPUT_DIR, banner, print_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="render only this seeded template code")
    parser.add_argument("--file", help="ingest and render this .docx instead of the defaults")
    parser.add_argument("--primary", default="ENG", help="primary language for --file")
    parser.add_argument("--secondary", default="UKR", help="secondary language for --file")
    parser.add_argument("--type", default="invoice", help="document type code for --file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    banner("1. Initialise database (migrate + seed reference data + seed templates)")
    scenario.initialise()

    from sqlalchemy import select

    from app.assets.provider import DbAssetProvider
    from app.db.models.core.document_sequence import DocumentSequence
    from app.db.models.core.template import Template
    from app.db.session import SessionLocal
    from app.document_engine.blueprint.models.template import TemplateConfig
    from app.document_engine.orchestration.pipeline import TemplateRenderingPipeline
    from app.services.invoice.assembler import (
        InvoiceAssembler, build_labels, resolve_languages,
    )
    from app.services.invoice.mapper import InvoiceMapper
    from app.services.template.db_input_provider import DbTemplateInputProvider
    from app.services.template.import_service import TemplateImportService
    from app.services.template.repository import TemplateRepository

    banner("2. Insert user data (organisations, invoice lines, document sequence)")
    with SessionLocal() as session:
        session.add(scenario.default_template_config(
            primary=args.primary, secondary=args.secondary, document_type=args.type,
        ))
        session.commit()

        # the legal form lives in org_type, so the names must not repeat it
        provider = scenario.sample_organisation(
            session, "Acme Software", "Акме Софтвер", "12345678",
        )
        client = scenario.sample_organisation(
            session, "Globex Trading", "Глобекс Трейдинг", "87654321",
            with_bank=False,
        )
        lines = scenario.sample_invoice_lines(session)
        session.flush()

        sequence = DocumentSequence(
            document_type_code=args.type, organization_id=provider.id,
            prefix="INV-", counter=41, padding=5,
        )
        session.add(sequence)
        session.commit()

        provider_id, client_id, sequence_id = provider.id, client.id, sequence.id
        line_ids = [line.id for line in lines]
        print(f"   provider={provider_id} client={client_id} "
              f"lines={line_ids} sequence={sequence_id}")

    banner("3. Choose the template(s)")
    with SessionLocal() as session:
        if args.file:
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
            repository = TemplateRepository(session)
            template = session.get(Template, template_id)
            blueprint = repository.get(template_id)

            banner(f"4. {template.code or template.name} — assemble and render")

            languages = resolve_languages(session, blueprint.config)
            print(f"   languages: {[(l.code, l.alpha_2) for l in languages]}")

            draft = scenario.sample_draft(
                _organisation(session, provider_id),
                _organisation(session, client_id),
                session.get(DocumentSequence, sequence_id),
                line_ids,
                issue_date=date(2026, 8, 3),
            )

            data = InvoiceAssembler(session, languages).assemble(draft)
            labels = build_labels(session, tuple(l.code for l in languages))
            context = InvoiceMapper(
                languages, labels, blueprint.config.append_currency,
            ).map(data)

            print(f"   invoice {data.prefix}{data.number}, {len(data.lines)} line(s)")
            for key in ("date", "curr", "subtotal", "total_tax", "total", "total_text"):
                if key in context.scalars:
                    print(f"   {key:<12} {context.scalars[key]}")

            render = TemplateRenderingPipeline(DbAssetProvider(session)).render(
                blueprint, context,
            )
            for item in render.diagnostics.items:
                print(f"   [{item.severity}] {item.code}: {item.message}")

            if render.docx is None:
                print("   RENDER FAILED")
                failures += 1
                continue

            out = OUTPUT_DIR / f"{template.code or template_id}.docx"
            out.write_bytes(render.docx)
            print(f"   wrote {len(render.docx):,} bytes -> {out}")

            print_document(out)

            text = scenario.describe_docx(out)
            leftovers = sorted({
                line.strip() for line in text.splitlines() if "{{" in line
            })
            print(f"\n   unresolved placeholders: {leftovers or 'none'}")

    banner("done")
    print(f"   output: {OUTPUT_DIR}")
    return 1 if failures else 0


def _organisation(session, organization_id: int):
    from app.db.models.core.organization import Organization

    return session.get(Organization, organization_id)


if __name__ == "__main__":
    raise SystemExit(main())
