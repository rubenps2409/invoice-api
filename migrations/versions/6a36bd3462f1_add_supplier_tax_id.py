"""add supplier tax id

Revision ID: 6a36bd3462f1
Revises: 63f99d6f3e25
Create Date: 2026-10-26 00:43:33.407131

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6a36bd3462f1'
down_revision: str | Sequence[str] | None = '63f99d6f3e25'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('suppliers', sa.Column('tax_id', sa.String(length=20), nullable=True))
    op.create_unique_constraint('uq_supplier_tax_id_user_id', 'suppliers', ['tax_id', 'user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_supplier_tax_id_user_id', 'suppliers', type_='unique')
    op.drop_column('suppliers', 'tax_id')
