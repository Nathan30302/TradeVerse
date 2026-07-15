"""
Detect optional migrated schema so the ORM matches the live database.

Deferred columns still participate in INSERT/UPDATE by default; `app.orm_hooks`
strips missing columns from collected SQL params and temporarily clears Python
Column defaults during flush so compiled INSERTs omit absent columns until
`flask db upgrade` runs.

When Alembic lags on Render, ``ensure_lagging_schema`` adds critical columns/tables
so the app stays usable.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Tuple

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

# (SQL type, optional DEFAULT literal for ADD COLUMN)
_USER_COLUMN_DDL: Dict[str, Tuple[str, Optional[str]]] = {
    "role": ("VARCHAR(20)", "'user'"),
    "subscription_tier": ("VARCHAR(20)", "'free'"),
    "subscription_status": ("VARCHAR(20)", "'active'"),
    "trial_ends_at": ("TIMESTAMP", None),
    "subscription_expires_at": ("TIMESTAMP", None),
    "stripe_customer_id": ("VARCHAR(255)", None),
    "weekly_focus_rule": ("TEXT", None),
    "signup_utm_source": ("VARCHAR(255)", None),
    "exports_blocked": ("BOOLEAN", "FALSE"),
    "country_code": ("VARCHAR(2)", None),
    "phone_number": ("VARCHAR(32)", None),
}

TRADE_OPTIONAL_COLUMNS: FrozenSet[str] = frozenset({"playbook_setup_id"})


def _clear_insp(insp) -> None:
    try:
        insp.clear_cache()
    except Exception:
        pass


def _add_column_if_missing(conn, dialect: str, table: str, column: str, coltype: str, default: Optional[str]) -> bool:
    """Return True if a column was added."""
    if dialect == "postgresql":
        if default is not None:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype} DEFAULT {default}"
        else:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"
        conn.execute(sa.text(sql))
        return True
    # SQLite / others: caller already checked absence
    if default is not None:
        sql = f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}"
    else:
        sql = f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
    conn.execute(sa.text(sql))
    return True


def ensure_user_optional_columns(app: Any) -> bool:
    """Add missing users.* optional columns (role, weekly_focus_rule, billing, …)."""
    from app import db

    try:
        insp = sa.inspect(db.engine)
        if not insp.has_table("users"):
            return False
        dialect = db.engine.dialect.name
        have = {c.get("name") for c in insp.get_columns("users")}
        missing = [c for c in _USER_COLUMN_DDL if c not in have]
        if not missing:
            return True

        with db.engine.begin() as conn:
            for col in missing:
                coltype, default = _USER_COLUMN_DDL[col]
                try:
                    _add_column_if_missing(conn, dialect, "users", col, coltype, default)
                    app.logger.info("schema_compat: added users.%s", col)
                except Exception as exc:
                    app.logger.warning("schema_compat: could not add users.%s: %s", col, exc)
            # Backfill role if present
            if "role" in missing or "role" not in have:
                try:
                    conn.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))
                except Exception:
                    pass
            if "subscription_tier" in missing:
                try:
                    conn.execute(
                        sa.text(
                            "UPDATE users SET subscription_tier = 'free' WHERE subscription_tier IS NULL"
                        )
                    )
                except Exception:
                    pass
            if "subscription_status" in missing:
                try:
                    conn.execute(
                        sa.text(
                            "UPDATE users SET subscription_status = 'active' WHERE subscription_status IS NULL"
                        )
                    )
                except Exception:
                    pass

        _clear_insp(insp)
        try:
            db.session.rollback()
        except Exception:
            pass
        return True
    except Exception as exc:
        app.logger.warning("schema_compat: ensure_user_optional_columns failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def ensure_ai_coaching_notes(app: Any) -> bool:
    """Create ai_coaching_notes if missing."""
    from app import db

    try:
        insp = sa.inspect(db.engine)
        if insp.has_table("ai_coaching_notes"):
            return True
        table = sa.Table(
            "ai_coaching_notes",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("pinned_rule", sa.Text(), nullable=False, server_default=""),
            sa.Column("checklist_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        table.create(bind=db.engine, checkfirst=True)
        try:
            sa.Index("ix_ai_coaching_notes_user_id", table.c.user_id).create(bind=db.engine)
        except Exception:
            pass
        app.logger.info("schema_compat: created ai_coaching_notes table")
        _clear_insp(insp)
        try:
            db.session.rollback()
        except Exception:
            pass
        return True
    except Exception as exc:
        app.logger.warning("schema_compat: ensure_ai_coaching_notes failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


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
                    _add_column_if_missing(conn, dialect, "playbook_setups", "example_images", "TEXT", "'[]'")
                created_anything = True
                app.logger.info("schema_compat: added playbook_setups.example_images")

        if insp.has_table("trades"):
            _clear_insp(insp)
            insp = sa.inspect(db.engine)
            trade_cols = {c.get("name") for c in insp.get_columns("trades")}
            if "playbook_setup_id" not in trade_cols:
                with db.engine.begin() as conn:
                    _add_column_if_missing(conn, dialect, "trades", "playbook_setup_id", "INTEGER", None)
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
            _clear_insp(insp)

        return True
    except Exception as exc:
        app.logger.warning("schema_compat: ensure_playbook_schema failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def ensure_lagging_schema(app: Any) -> None:
    """Best-effort create of columns/tables Alembic may not have applied yet."""
    ensure_user_optional_columns(app)
    ensure_ai_coaching_notes(app)
    ensure_playbook_schema(app)
    refresh(app)


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
        flags["ai_coaching_ready"] = bool(insp.has_table("ai_coaching_notes"))

        app.extensions["tradeverse_schema"] = flags
        if flags["omit_user_cols"]:
            app.logger.warning(
                "schema_compat: users missing columns %s (will stamp defaults on load)",
                sorted(flags["omit_user_cols"]),
            )
    except Exception as exc:
        app.logger.warning(
            "tradeverse_schema: inspection failed (%s); disabling optional CRM columns temporarily",
            exc,
        )
        flags["omit_user_cols"] = USER_OPTIONAL_COLUMNS
        flags["omit_trade_cols"] = TRADE_OPTIONAL_COLUMNS
        app.extensions["tradeverse_schema"] = flags
    return flags
