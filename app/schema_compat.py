"""
Detect optional migrated schema so the ORM matches the live database.

Deferred columns still participate in INSERT/UPDATE by default; `app.orm_hooks`
strips missing columns from collected SQL params and temporarily clears Python
Column defaults during flush so compiled INSERTs omit absent columns until
`flask db upgrade` runs.
"""

from __future__ import annotations

from typing import Any, FrozenSet

import sqlalchemy as sa

# Mapped on User — often added after deferred billing/coach migrations.
USER_OPTIONAL_COLUMNS: FrozenSet[str] = frozenset(
    {
        "role",
        "subscription_tier",
        "subscription_status",
        "trial_ends_at",
        "subscription_expires_at",
        "stripe_customer_id",
        "weekly_focus_rule",
        "signup_utm_source",
        "exports_blocked",
        "country_code",
        "phone_number",
    }
)

TRADE_OPTIONAL_COLUMNS: FrozenSet[str] = frozenset({"playbook_setup_id"})


def ensure_playbook_schema(app: Any) -> bool:
    """
    Create playbook tables/columns if migrations lagged (common on Render).

    Idempotent. Returns True when the ensure step completed without a hard failure.
    """
    from app import db

    try:
        insp = sa.inspect(db.engine)
        dialect = db.engine.dialect.name
        created_anything = False

        if not insp.has_table("playbook_setups"):
            bool_type = sa.Boolean()
            table = sa.Table(
                "playbook_setups",
                sa.MetaData(),
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
                sa.Column("name", sa.String(140), nullable=False, server_default=""),
                sa.Column("market", sa.String(40), nullable=False, server_default=""),
                sa.Column("symbol_hint", sa.String(40), nullable=False, server_default=""),
                sa.Column("timeframe", sa.String(16), nullable=False, server_default=""),
                sa.Column("entry_criteria", sa.Text(), nullable=False, server_default=""),
                sa.Column("invalidation", sa.Text(), nullable=False, server_default=""),
                sa.Column("management_plan", sa.Text(), nullable=False, server_default=""),
                sa.Column("checklist_text", sa.Text(), nullable=False, server_default=""),
                sa.Column("tags", sa.String(180), nullable=False, server_default=""),
                sa.Column("is_active", bool_type, nullable=False, server_default=sa.true()),
                sa.Column("example_images", sa.Text(), nullable=False, server_default="[]"),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=True),
            )
            table.create(bind=db.engine, checkfirst=True)
            try:
                sa.Index("ix_playbook_setups_user_id", table.c.user_id).create(bind=db.engine)
            except Exception:
                pass
            created_anything = True
            app.logger.info("schema_compat: created playbook_setups table")
        else:
            pb_cols = {c.get("name") for c in insp.get_columns("playbook_setups")}
            if "example_images" not in pb_cols:
                with db.engine.begin() as conn:
                    if dialect == "postgresql":
                        conn.execute(
                            sa.text(
                                "ALTER TABLE playbook_setups "
                                "ADD COLUMN IF NOT EXISTS example_images TEXT DEFAULT '[]'"
                            )
                        )
                    else:
                        conn.execute(
                            sa.text(
                                "ALTER TABLE playbook_setups ADD COLUMN example_images TEXT DEFAULT '[]'"
                            )
                        )
                created_anything = True
                app.logger.info("schema_compat: added playbook_setups.example_images")

        if insp.has_table("trades"):
            # Re-inspect after possible table create
            try:
                insp.clear_cache()
            except Exception:
                pass
            insp = sa.inspect(db.engine)
            trade_cols = {c.get("name") for c in insp.get_columns("trades")}
            if "playbook_setup_id" not in trade_cols:
                with db.engine.begin() as conn:
                    if dialect == "postgresql":
                        conn.execute(
                            sa.text(
                                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS playbook_setup_id INTEGER"
                            )
                        )
                    else:
                        conn.execute(sa.text("ALTER TABLE trades ADD COLUMN playbook_setup_id INTEGER"))
                try:
                    with db.engine.begin() as conn:
                        conn.execute(
                            sa.text(
                                "CREATE INDEX IF NOT EXISTS ix_trades_playbook_setup_id "
                                "ON trades (playbook_setup_id)"
                            )
                        )
                except Exception:
                    pass
                created_anything = True
                app.logger.info("schema_compat: added trades.playbook_setup_id")

        if created_anything:
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                insp.clear_cache()
            except Exception:
                pass

        return True
    except Exception as exc:
        app.logger.warning("schema_compat: ensure_playbook_schema failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def refresh(app: Any) -> dict[str, Any]:
    """Populate app.extensions[\"tradeverse_schema\"] from the live database."""
    from app import db

    flags: dict[str, Any] = {
        "playbook_ready": False,
        "replay_ready": False,
        "omit_user_cols": frozenset(),
        "omit_trade_cols": frozenset(),
    }
    try:
        insp = sa.inspect(db.engine)
        omit_user = set(USER_OPTIONAL_COLUMNS)
        omit_trade = set(TRADE_OPTIONAL_COLUMNS)

        if insp.has_table("users"):
            have_u = {c.get("name") for c in insp.get_columns("users")}
            omit_user = {c for c in USER_OPTIONAL_COLUMNS if c not in have_u}
        else:
            omit_user = set(USER_OPTIONAL_COLUMNS)

        if insp.has_table("trades"):
            have_t = {c.get("name") for c in insp.get_columns("trades")}
            omit_trade = {c for c in TRADE_OPTIONAL_COLUMNS if c not in have_t}
        else:
            omit_trade = set(TRADE_OPTIONAL_COLUMNS)

        has_pb = insp.has_table("playbook_setups")
        has_setup_col = "playbook_setup_id" in (
            {c.get("name") for c in insp.get_columns("trades")} if insp.has_table("trades") else set()
        )

        flags["omit_user_cols"] = frozenset(omit_user)
        flags["omit_trade_cols"] = frozenset(omit_trade)
        flags["playbook_ready"] = bool(has_pb and has_setup_col)
        flags["replay_ready"] = bool(insp.has_table("trade_replay_events"))

        app.extensions["tradeverse_schema"] = flags
    except Exception as exc:
        app.logger.warning(
            "tradeverse_schema: inspection failed (%s); disabling optional CRM columns temporarily",
            exc,
        )
        flags["omit_user_cols"] = USER_OPTIONAL_COLUMNS
        flags["omit_trade_cols"] = TRADE_OPTIONAL_COLUMNS
        app.extensions["tradeverse_schema"] = flags
    return flags
