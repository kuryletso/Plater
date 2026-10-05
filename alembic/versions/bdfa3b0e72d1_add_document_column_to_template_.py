"""Add document column to template_versions table.

Revision ID: bdfa3b0e72d1
Revises: 72d7bd86c2e7
Create Date: 2026-09-29 21:50:47.333818

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdfa3b0e72d1'
down_revision: Union[str, Sequence[str], None] = '72d7bd86c2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Document-level blueprint data: page color, embedded fonts etc. The server default gives 
    # versions stored before this column an empty object, which loads as "no page color"
    with op.batch_alter_table('template_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))

def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('template_versions', schema=None) as batch_op:
        batch_op.drop_column('document')