"""add imported_source_id to trades

Revision ID: 20251212_add_imported_source_fk_to_trades
Revises: 20251212_add_instrument_aliases
Create Date: 2025-12-12 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251212_add_imported_source_fk_to_trades'
down_revision = '20251212_add_broker_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Add imported_source_id column and foreign key to imported_trade_sources
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('imported_source_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_trades_imported_source', 'imported_trade_sources', ['imported_source_id'], ['id'])
        batch_op.create_index(op.f('ix_trades_imported_source_id'), ['imported_source_id'])


def downgrade():
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.drop_constraint('fk_trades_imported_source', type_='foreignkey')
        batch_op.drop_index(op.f('ix_trades_imported_source_id'))
        batch_op.drop_column('imported_source_id')
