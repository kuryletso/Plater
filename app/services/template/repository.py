from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.assets.repository import save_assets
from app.assets.service import AssetBlob
from app.db.associations import template_version_asset_m2m
from app.db.models.core.assets import Asset
from app.db.models.core.template import Template
from app.db.models.core.template_version import TemplateVersion
from app.document_engine.blueprint.models.template import TemplateBlueprint
from app.document_engine.blueprint.assets import collect_assets_ids
from app.document_engine.blueprint.serialize import dump_blueprint, load_blueprint
from app.services.errors import EntityNotFound


class TemplateRepository:

    KEEP_VERSIONS = 3

    def __init__(
            self,
            session: Session,
    ) -> None:
        
        self._session = session

    def create(
            self,
            blueprint: TemplateBlueprint,
            bundle: Mapping[str, AssetBlob],
            source: AssetBlob,
            *,
            code: str | None = None,
            system: bool = False,
    ) -> int:

        template = Template(
            code=code,
            name=blueprint.config.name,
            type=blueprint.config.type,
            system=system,
        )
        self._session.add(template)
        self._session.flush()

        self._add_version(template.id, 1, blueprint, bundle, source)
        self._session.commit()

        return template.id

    def add_version(
            self,
            template_id: int,
            blueprint: TemplateBlueprint,
            bundle: Mapping[str, AssetBlob],
            source: AssetBlob,
    ) -> int:

        current = self.current_version(template_id)
        version = current.version + 1

        self._add_version(template_id, version, blueprint, bundle, source)
        self._prune(template_id)
        self._collect_orphans()
        self._session.commit()

        return version

    def _add_version(
            self,
            template_id: int,
            version: int,
            blueprint: TemplateBlueprint,
            bundle: Mapping[str, AssetBlob],
            source: AssetBlob,
    ) -> TemplateVersion:

        sections, placeholders, config = dump_blueprint(blueprint)

        row = TemplateVersion(
            template_id=template_id,
            version=version,
            source_sha256=source.sha256,
            sections=sections,
            placeholders=placeholders,
            config=config,
        )
        self._session.add(row)
        self._session.flush()

        referenced = collect_assets_ids(blueprint)
        save_assets(
            self._session,
            {source.sha256: source} | { h: bundle[h] for h in referenced if h in bundle },
        )

        for sha in referenced | {source.sha256}:
            self._session.execute(
                template_version_asset_m2m.insert().values(
                    template_version_id=row.id,
                    asset_sha256=sha,
                )
            )

        return row


    def current_version(self, template_id: int) -> TemplateVersion:
        row = self._session.scalars(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == template_id)
            .order_by(TemplateVersion.version.desc())
            .limit(1)
        ).first()

        if row is None:
            raise EntityNotFound(
                f"template {template_id} has no versions",
                context={"template_id": template_id},
            )
        return row


    def get(self, template_id: int) -> TemplateBlueprint:
        row = self.current_version(template_id)
        return load_blueprint(row.sections, row.placeholders, row.config)


    def restore(self, template_id: int, version: int) -> int:
        """Copy an old version forward as the newest, history stays append-only."""

        old = self._version(template_id, version)
        blueprint = load_blueprint(old.sections, old.placeholders, old.config)

        return self.add_version(
            template_id, blueprint, {}, self._source_blob(old.source_sha256),
        )


    def delete(self, template_id: int) -> None:

        template = self._session.get(Template, template_id)

        if template is None:
            raise EntityNotFound(
                f"template {template_id} not found",
                context={"template_id": template_id},
            )

        version_ids = select(TemplateVersion.id).where(
            TemplateVersion.template_id == template_id,
        )
        self._session.execute(
            delete(template_version_asset_m2m).where(
                template_version_asset_m2m.c.template_version_id.in_(version_ids),
            )
        )
        self._session.delete(template)
        self._session.flush()

        self._collect_orphans()
        self._session.commit()


    def _prune(self, template_id: int) -> None:
        versions = self._session.scalars(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == template_id)
            .order_by(TemplateVersion.version.desc())
        ).all()

        for old in versions[self.KEEP_VERSIONS:]:
            self._session.execute(
                delete(template_version_asset_m2m).where(
                    template_version_asset_m2m.c.template_version_id == old.id,
                )
            )
            self._session.delete(old)

        self._session.flush()


    def _collect_orphans(self) -> None:
        referenced = select(template_version_asset_m2m.c.asset_sha256)
        self._session.execute(delete(Asset).where(Asset.sha256.not_in(referenced)))


    def _version(self, template_id: int, version: int) -> TemplateVersion:
        row = self._session.scalars(
            select(TemplateVersion).where(
                TemplateVersion.template_id == template_id,
                TemplateVersion.version == version,
            )
        ).first()

        if row is None:
            raise EntityNotFound(
                f"temlpate {template_id} has no version {version}",
                context={"template_id": template_id, "version": version},
            )
        return row


    def _source_blob(self, sha256: str) -> AssetBlob:
        row = self._session.get(Asset, sha256)

        if row is None:
            raise EntityNotFound(
                f"source document {sha256} is not stored",
                context={"sha256": sha256},
            )

        return AssetBlob(
            sha256=sha256,
            mime_type=row.mime_type,
            data=row.data,
        )


    def get_source(
            self,
            template_id: int,
            version: int | None = None,
    ) -> AssetBlob:
        """The original .docx, for restoring the file the template was built from."""

        row = self.current_version(template_id) \
            if version is None \
            else self._version(template_id, version)

        return self._source_blob(row.source_sha256)