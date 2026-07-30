from sqlalchemy import Table, Column, ForeignKey

from app.db.base import Base

organization_representative_m2m = Table(
    "organization_representative_association",
    Base.metadata,
    Column(
        "organization_id",
        ForeignKey("organizations.id"),
        primary_key=True
    ),
    Column(
        "representative_id",
        ForeignKey("representatives.id"),
        primary_key=True
    )
)


template_version_asset_m2m = Table(
    "template_version_assets",
    Base.metadata,
    Column("template_version_id", ForeignKey("template_versions.id"), primary_key=True),
    Column("asset_sha256", ForeignKey("assets.sha256"), primary_key=True),
)