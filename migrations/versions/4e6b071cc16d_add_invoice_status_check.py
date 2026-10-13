"""add invoice status check

Revision ID: 4e6b071cc16d
Revises: 69a109d7619d
Create Date: 2026-10-13 00:21:04.154441

"""
from collections.abc import Sequence

from alembic import op

revision: str = '4e6b071cc16d'
down_revision: str | Sequence[str] | None = '69a109d7619d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_invoices_invoicestatus"),
        "invoices",
        "status IN ('pending', 'paid', 'partially_paid', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_invoices_invoicestatus"), "invoices", type_="check")
