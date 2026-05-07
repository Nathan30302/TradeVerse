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
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table('trades'):
        return

    # SQLite safety: clean up leftover temp table from a failed batch op.
    try:
        op.execute("DROP TABLE IF EXISTS _alembic_tmp_trades")
    except Exception:
        pass

    cols = {c['name'] for c in insp.get_columns('trades')}
    indexes = {ix.get('name') for ix in insp.get_indexes('trades')}
    fks = {fk.get('name') for fk in insp.get_foreign_keys('trades')}

    with op.batch_alter_table('trades', schema=None) as batch_op:
        if 'imported_source_id' not in cols:
            batch_op.add_column(sa.Column('imported_source_id', sa.Integer(), nullable=True))
        if 'fk_trades_imported_source' not in fks:
            batch_op.create_foreign_key('fk_trades_imported_source', 'imported_trade_sources', ['imported_source_id'], ['id'])
        if op.f('ix_trades_imported_source_id') not in indexes:
            batch_op.create_index(op.f('ix_trades_imported_source_id'), ['imported_source_id'])


def downgrade():
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.drop_constraint('fk_trades_imported_source', type_='foreignkey')
        batch_op.drop_index(op.f('ix_trades_imported_source_id'))
        batch_op.drop_column('imported_source_id')
