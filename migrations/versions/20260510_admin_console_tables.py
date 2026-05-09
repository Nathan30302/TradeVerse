"""admin console tables + user signup/export flags

Revision ID: 20260510_admin_console
Revises: 20260508_trade_replay
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_admin_console"
down_revision = "20260508_trade_replay"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("admin_console_events"):
        op.create_table(
            "admin_console_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        try:
            op.create_index("ix_admin_console_events_event_type", "admin_console_events", ["event_type"])
        except Exception:
            pass
        try:
            op.create_index("ix_admin_console_events_created_at", "admin_console_events", ["created_at"])
        except Exception:
            pass

    if not insp.has_table("admin_email_drafts"):
        op.create_table(
            "admin_email_drafts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("subject", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("audience_hint", sa.String(length=40), nullable=True, server_default="test_self"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    insp = sa.inspect(bind)
    ucols = set()
    try:
        ucols = {c.get("name") for c in insp.get_columns("users")}
    except Exception:
        ucols = set()
    if "exports_blocked" not in ucols:
        try:
            op.add_column(
                "users",
                sa.Column("exports_blocked", sa.Boolean(), nullable=True, server_default=sa.text("0")),
            )
        except Exception:
            pass
    if "signup_utm_source" not in ucols:
        try:
            op.add_column("users", sa.Column("signup_utm_source", sa.String(length=255), nullable=True))
        except Exception:
            pass


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("admin_email_drafts"):
        op.drop_table("admin_email_drafts")
    if insp.has_table("admin_console_events"):
        op.drop_table("admin_console_events")
    ucols = set()
    try:
        ucols = {c.get("name") for c in insp.get_columns("users")}
    except Exception:
        ucols = set()
    if "signup_utm_source" in ucols:
        try:
            op.drop_column("users", "signup_utm_source")
        except Exception:
            pass
    if "exports_blocked" in ucols:
        try:
            op.drop_column("users", "exports_blocked")
        except Exception:
            pass
