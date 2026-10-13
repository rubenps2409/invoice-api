"""create initial tables

Revision ID: 69a109d7619d
Revises: 
Create Date: 2026-10-11 21:46:30.731258

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '69a109d7619d'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_categories_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('name', 'user_id', name='uq_category_name_user_id')
    )
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)
    op.create_table('suppliers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_suppliers_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers')),
    sa.UniqueConstraint('name', 'user_id', name='uq_supplier_name_user_id')
    )
    op.create_index(op.f('ix_suppliers_user_id'), 'suppliers', ['user_id'], unique=False)
    op.create_table('invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('base_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('issue_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'paid', 'partially_paid', 'cancelled', name='invoicestatus', native_enum=False, length=20), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_invoices_category_id_categories')),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_invoices_supplier_id_suppliers')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_invoices_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
    sa.UniqueConstraint('user_id', 'supplier_id', 'number', name='uq_invoice_user_supplier_number')
    )
    op.create_index(op.f('ix_invoices_category_id'), 'invoices', ['category_id'], unique=False)
    op.create_index(op.f('ix_invoices_supplier_id'), 'invoices', ['supplier_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_invoices_supplier_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_category_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_suppliers_user_id'), table_name='suppliers')
    op.drop_table('suppliers')
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_table('users')
