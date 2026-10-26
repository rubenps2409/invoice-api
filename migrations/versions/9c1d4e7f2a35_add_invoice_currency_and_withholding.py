"""add invoice currency and withholding

Revision ID: 9c1d4e7f2a35
Revises: 6a36bd3462f1
Create Date: 2026-10-26 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9c1d4e7f2a35'
down_revision: str | Sequence[str] | None = '6a36bd3462f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing invoices get EUR and no withholding. The defaults are only there
    # to fill them in: the application always provides both values.
    op.add_column(
        'invoices',
        sa.Column('withholding_amount', sa.Numeric(precision=10, scale=2),
                  server_default='0', nullable=False),
    )
    op.add_column(
        'invoices',
        sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
    )
    op.alter_column('invoices', 'withholding_amount', server_default=None)
    op.alter_column('invoices', 'currency', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices', 'currency')
    op.drop_column('invoices', 'withholding_amount')
