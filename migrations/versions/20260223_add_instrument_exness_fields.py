"""add instrument exness fields

Revision ID: 20260223_add_instrument_exness_fields
Revises: 07e766313e36
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260223_add_instrument_exness_fields'
down_revision = '07e766313e36'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_currency', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('quote_currency', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('lot_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('lot_max', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('lot_step', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('tick_size', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('margin_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('pnl_method', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.drop_column('pnl_method')
        batch_op.drop_column('margin_rate')
        batch_op.drop_column('tick_size')
        batch_op.drop_column('lot_step')
        batch_op.drop_column('lot_max')
        batch_op.drop_column('lot_min')
        batch_op.drop_column('quote_currency')
        batch_op.drop_column('base_currency')
