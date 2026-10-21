"""Add date_format column to default_template_config

Revision ID: cf9a27f30ffd
Revises: bdfa3b0e72d1
Create Date: 2026-10-21 18:58:13.307673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf9a27f30ffd'
down_revision: Union[str, Sequence[str], None] = 'bdfa3b0e72d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('default_template_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_format', sa.String(length=20), server_default='y-MM-dd', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('default_template_config', schema=None) as batch_op:
        batch_op.drop_column('date_format')