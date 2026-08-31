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
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.document_engine.blueprint.models.template import TemplateBlueprint
from app.document_engine.blueprint.assets import collect_assets_ids
from app.document_engine.blueprint.serialize import dump_blueprint, load_blueprint
from app.services.errors import EntityNotFound, InvalidSelection
from app.services.sentinel import Unset, UNSET

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
        """Append a user-authored version. Built-in templates are read-only."""

        if self._template(template_id).system:
            raise InvalidSelection(
                f"template {template_id} is built in and cannot be edited",
                user_message="This is a built-in template. Make a copy to edit it.",
                context={"template_id": template_id},
            )

        return self._append_version(template_id, blueprint, bundle, source)


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


    def sync_system_version(
            self,
            template_id: int,
            blueprint: TemplateBlueprint,
            bundle: Mapping[str, AssetBlob],
            source: AssetBlob,
    ) -> int:
        """Update a shipped default from its new .docx. Seeding only."""

        if not self._template(template_id).system:
            raise InvalidSelection(
                f"template {template_id} is not built-in template",
                context={"template_id": template_id},
            )

        return self._append_version(template_id, blueprint, bundle, source)


    def _append_version(
            self,
            template_id: int,
            blueprint: TemplateBlueprint,
            bundle: Mapping[str, AssetBlob],
            source: AssetBlob,
    ) -> int:

        version = self.current_version(template_id).version + 1

        self._add_version(template_id, version, blueprint, bundle, source)
        self._prune(template_id)
        self._collect_orphans()
        self._session.commit()

        return version


    def get(self, template_id: int) -> Template:
        template = self._session.get(Template, template_id)
        if template is None:
            raise EntityNotFound(
                f"template {template_id!r} not found",
                context={"template_id": template_id},
            )

        return template


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


    def get_blueprint(self, template_id: int) -> TemplateBlueprint:
        row = self.current_version(template_id)
        return load_blueprint(row.sections, row.placeholders, row.config)


    def _template(
            self,
            template_id: int,
    ) -> Template:

        template = self._session.get(Template, template_id)
        if template is None:
            raise EntityNotFound(
                f"template {template_id} not found",
                context={"template_id": template_id},
            )
        return template


    def restore(self, template_id: int, version: int) -> int:
        """Copy an old version forward as the newest, history stays append-only."""

        old = self._version(template_id, version)
        blueprint = load_blueprint(old.sections, old.placeholders, old.config)

        return self.add_version(
            template_id, blueprint, {}, self._source_blob(old.source_sha256),
        )


    def delete(self, template_id: int) -> None:

        template = self._template(template_id)

        if template.system:
            raise InvalidSelection(
                f"template {template_id} is built in and cannot be deleted",
                user_message="Built in templates can only be hidden, not deleted.",
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


    def update_metadata(
            self,
            template_id: int,
            *,
            name: str | Unset = UNSET,
            document_type: str | Unset = UNSET,
            description: str | Unset = UNSET,
            append_currency: bool | Unset = UNSET,
    ) -> Template:
        """Edits name, type and description etc. without touching its blueprint.
        
        Languages are deliberately absent: they are baked in at ingestion. 
        Changing them is only supported via new version (add_version() method).
        """

        template = self.get(template_id)

        if template.system:
            raise InvalidSelection(
                f"template {template_id} is built in and cannot be edited",
                user_message="This is a built-in template. Make a copy of it to edit.",
                context={"template_id": template_id},
            )

        if not isinstance(document_type, Unset):
            self._check_document_type(document_type)

        version = self.current_version(template_id)
        config = dict(version.config)

        if not isinstance(name, Unset):
            template.name = name

        if not isinstance(document_type, Unset):
            template.type = document_type

        if not isinstance(description, Unset):
            config["description"] = description

        if not isinstance(append_currency, Unset):
            config["append_currency"] = append_currency

        version.config = config
        self._session.commit()

        return template


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


    def copy(
            self,
            template_id: int,
            name: str,
    ) -> int:
        """Derive an editable, user-owned template from an existing one.
        
        Only the current version is copied, the copy starts its own history.
        Assets are shared by hash, so nothing is duplicated in storage.
        """

        origin = self._template(template_id)

        current = self.current_version(template_id)

        template = Template(
            code=None,
            name=name,
            type=origin.type,
            system=False,
        )

        self._session.add(template)
        self._session.flush()

        row = TemplateVersion(
            template_id=template.id,
            version=1,
            source_sha256=current.source_sha256,
            sections=current.sections,
            placeholders=current.placeholders,
            config=dict(current.config) | {"name": name},
        )
        self._session.add(row)
        self._session.flush()

        linked = self._session.execute(
            select(template_version_asset_m2m.c.asset_sha256)
            .where(template_version_asset_m2m.c.template_version_id == current.id)
        ).scalars().all()

        for sha in linked:
            self._session.execute(
                template_version_asset_m2m.insert().values(
                    template_version_id=row.id,
                    asset_sha256=sha,
                )
            )

        self._session.commit()

        return template.id


    def deactivate(
            self,
            template_id: int,
    ) -> None:
        """Hide a template without destroying it. The only removal flow for built-ins."""

        self._template(template_id).active = False
        self._session.commit()


    def activate(
            self,
            template_id: int,
    ) -> None:

        self._template(template_id).active = True
        self._session.commit()


    def list(
            self,
            *,
            search: str | None = None,
            document_type: str | None = None,
            include_inactive: bool = False,
    ) -> list[Template]:
        """Newest first; 'search' matches the template name."""

        query = select(Template).order_by(Template.id.desc())

        if not include_inactive:
            query = query.where(Template.active.is_(True))
        if document_type is not None:
            query = query.where(Template.type == document_type)
        if search:
            query = query.where(Template.name.icontains(search))

        return list(self._session.scalars(query).all())


    def _check_document_type(self, code: str) -> None:
        row = self._session.get(DocumentTypeRegistry, code)

        if row is None:
            raise EntityNotFound(
                f"document type {code!r} not found",
                context={"code": code},
            )

        if not row.active:
            raise InvalidSelection(
                f"document type {code!r} is disabled",
                user_message="Selected document type is no longer available.",
                context={"code": code},
            )