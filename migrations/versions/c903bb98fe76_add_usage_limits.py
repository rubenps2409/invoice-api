"""add usage limits

Revision ID: c903bb98fe76
Revises: 9c1d4e7f2a35
Create Date: 2026-10-26 03:14:07.903417

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c903bb98fe76'
down_revision: str | Sequence[str] | None = '9c1d4e7f2a35'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('rate_limit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rate_limit_events'))
    )
    op.create_index('ix_rate_limit_events_action_key_hash_created_at', 'rate_limit_events', ['action', 'key_hash', 'created_at'], unique=False)
    op.create_index('ix_rate_limit_events_created_at', 'rate_limit_events', ['created_at'], unique=False)
    # The daily budget sums the cost per user and in total since midnight. The
    # (user_id, created_at) index replaces the old user_id-only one.
    op.drop_index(op.f('ix_llm_calls_user_id'), table_name='llm_calls')
    op.create_index('ix_llm_calls_created_at', 'llm_calls', ['created_at'], unique=False)
    op.create_index('ix_llm_calls_user_id_created_at', 'llm_calls', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_llm_calls_user_id_created_at', table_name='llm_calls')
    op.drop_index('ix_llm_calls_created_at', table_name='llm_calls')
    op.create_index(op.f('ix_llm_calls_user_id'), 'llm_calls', ['user_id'], unique=False)
    op.drop_index('ix_rate_limit_events_created_at', table_name='rate_limit_events')
    op.drop_index('ix_rate_limit_events_action_key_hash_created_at', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')
