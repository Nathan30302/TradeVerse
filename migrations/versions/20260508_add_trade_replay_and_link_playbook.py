"""add trade replay events and link trades to playbook setups

Revision ID: 20260508_trade_replay
Revises: 20260508_playbook_setups
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_trade_replay"
down_revision = "20260508_playbook_setups"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) trade_replay_events (idempotent)
    if not insp.has_table("trade_replay_events"):
        op.create_table(
            "trade_replay_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=False),
            sa.Column("event_type", sa.String(length=20), nullable=False, server_default="note"),
            sa.Column("occurred_at", sa.DateTime(), nullable=True),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("media_filename", sa.String(length=255), nullable=True),
            sa.Column("media_mimetype", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    # indexes (safe)
    try:
        ix = {x.get("name") for x in insp.get_indexes("trade_replay_events")}
    except Exception:
        ix = set()
    if "ix_trade_replay_events_user_id" not in ix:
        try:
            op.create_index("ix_trade_replay_events_user_id", "trade_replay_events", ["user_id"])
        except Exception:
            pass
    if "ix_trade_replay_events_trade_id" not in ix:
        try:
            op.create_index("ix_trade_replay_events_trade_id", "trade_replay_events", ["trade_id"])
        except Exception:
            pass
    if "ix_trade_replay_events_created_at" not in ix:
        try:
            op.create_index("ix_trade_replay_events_created_at", "trade_replay_events", ["created_at"])
        except Exception:
            pass

    # 2) trades.playbook_setup_id (idempotent for SQLite)
    cols = set()
    try:
        cols = {c.get("name") for c in insp.get_columns("trades")}
    except Exception:
        cols = set()
    if "playbook_setup_id" not in cols:
        try:
            op.add_column("trades", sa.Column("playbook_setup_id", sa.Integer(), nullable=True))
        except Exception:
            pass
        try:
            op.create_foreign_key(
                "fk_trades_playbook_setup_id",
                "trades",
                "playbook_setups",
                ["playbook_setup_id"],
                ["id"],
            )
        except Exception:
            pass
        try:
            op.create_index("ix_trades_playbook_setup_id", "trades", ["playbook_setup_id"])
        except Exception:
            pass


def downgrade():
    # Best-effort (SQLite limitations)
    try:
        op.drop_index("ix_trade_replay_events_created_at", table_name="trade_replay_events")
    except Exception:
        pass
    try:
        op.drop_index("ix_trade_replay_events_trade_id", table_name="trade_replay_events")
    except Exception:
        pass
    try:
        op.drop_index("ix_trade_replay_events_user_id", table_name="trade_replay_events")
    except Exception:
        pass
    try:
        op.drop_table("trade_replay_events")
    except Exception:
        pass

    try:
        op.drop_index("ix_trades_playbook_setup_id", table_name="trades")
    except Exception:
        pass
    try:
        op.drop_constraint("fk_trades_playbook_setup_id", "trades", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_column("trades", "playbook_setup_id")
    except Exception:
        pass

