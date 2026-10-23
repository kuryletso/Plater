"""Add label_en and label_uk to tax_id_system_registry

Revision ID: 2b350576ebe5
Revises: cf9a27f30ffd
Create Date: 2026-10-22 18:19:10.890121

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b350576ebe5'
down_revision: Union[str, Sequence[str], None] = 'cf9a27f30ffd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tax_id_system_registry', schema=None) as batch_op:
        batch_op.add_column(sa.Column('label_en', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('label_uk', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tax_id_system_registry', schema=None) as batch_op:
        batch_op.drop_column('label_uk')
        batch_op.drop_column('label_en')