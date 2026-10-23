"""One saved invoice line per description and language

Revision ID: a252e4850f1d
Revises: 2b350576ebe5
Create Date: 2026-10-23 14:15:44.143954

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a252e4850f1d'
down_revision: Union[str, Sequence[str], None] = '2b350576ebe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The saved lines are a hint cache full of duplicates. It's better to start it afresh rather than merge
    op.execute("DELETE FROM invoice_line_localizations")
    op.execute("DELETE FROM invoice_lines")

    with op.batch_alter_table("invoice_line_localizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description_key", sa.String(length=255), nullable=False))

        batch_op.create_unique_constraint(
            batch_op.f("uq_invoice_line_localizations_language_code"),
            ["language_code", "description_key"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("invoice_line_localizations", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("uq_invoice_line_localizations_language_code"),
            type_="unique",
        )
        batch_op.drop_column("description_key")