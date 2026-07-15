"""
Detect optional migrated schema so the ORM matches the live database.

When Alembic lags on Render, ``ensure_lagging_schema`` adds critical columns/tables
with raw SQL (no SQLAlchemy MetaData FK resolution — that fails when ``users`` is
not in the same MetaData).
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

# Stamp target when the live DB already has app tables but alembic_version is empty/stuck.
_TARGET_ALEMBIC_REV = "20260715_playbook_images"
_EARLY_ALEMBIC_REVS = frozenset(
    {
        "07e766313e36",
        "20251212_add_broker_tables",
        "20251212_add_imported_source_fk_to_trades",
        "20251212_add_instrument_aliases",
        "20251215_add_broker_system",
        "20260223_add_instrument_exness_fields",
        "45dc2b738986",
    }
)


def _clear_insp(insp) -> None:
    try:
        insp.clear_cache()
    except Exception:
        pass


def _dialect_name(engine) -> str:
    return (engine.dialect.name or "").lower()


def _add_column_sql(dialect: str, table: str, column: str, coltype: str, default: Optional[str]) -> str:
    if dialect == "postgresql":
        if default is not None:
            return f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype} DEFAULT {default}"
        return f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"
    if default is not None:
        return f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}"
    return f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"


def ensure_user_optional_columns(app: Any) -> bool:
    """Add missing users.* optional columns (role, weekly_focus_rule, billing, …)."""
    from app import db

    try:
        insp = sa.inspect(db.engine)
        if not insp.has_table("users"):
            app.logger.warning("schema_compat: users table missing; skip column ensure")
            return False
        dialect = _dialect_name(db.engine)
        have = {c.get("name") for c in insp.get_columns("users")}
        missing = [c for c in _USER_COLUMN_DDL if c not in have]
        if not missing:
            app.logger.info("schema_compat: users optional columns already present")
            return True

        app.logger.warning("schema_compat: adding missing users columns: %s", missing)
        with db.engine.begin() as conn:
            for col in missing:
                coltype, default = _USER_COLUMN_DDL[col]
                sql = _add_column_sql(dialect, "users", col, coltype, default)
                try:
                    conn.execute(sa.text(sql))
                    app.logger.warning("schema_compat: added users.%s", col)
                except Exception as exc:
                    # SQLite may error if column appeared concurrently; ignore duplicate-ish errors
                    app.logger.warning("schema_compat: could not add users.%s: %s", col, exc)
            try:
                conn.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))
            except Exception:
                pass
            try:
                conn.execute(
                    sa.text("UPDATE users SET subscription_tier = 'free' WHERE subscription_tier IS NULL")
                )
            except Exception:
                pass
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
    """Create ai_coaching_notes with raw SQL (no MetaData FK to users)."""
    from app import db

    try:
        insp = sa.inspect(db.engine)
        if insp.has_table("ai_coaching_notes"):
            return True
        dialect = _dialect_name(db.engine)
        if dialect == "postgresql":
            ddl = """
            CREATE TABLE IF NOT EXISTS ai_coaching_notes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                pinned_rule TEXT NOT NULL DEFAULT '',
                checklist_text TEXT NOT NULL DEFAULT '',
                source VARCHAR(30) NOT NULL DEFAULT 'manual',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NULL
            )
            """
        else:
            ddl = """
            CREATE TABLE IF NOT EXISTS ai_coaching_notes (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                pinned_rule TEXT NOT NULL DEFAULT '',
                checklist_text TEXT NOT NULL DEFAULT '',
                source VARCHAR(30) NOT NULL DEFAULT 'manual',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME
            )
            """
        with db.engine.begin() as conn:
            conn.execute(sa.text(ddl))
            try:
                conn.execute(
                    sa.text(
                        "CREATE INDEX IF NOT EXISTS ix_ai_coaching_notes_user_id "
                        "ON ai_coaching_notes (user_id)"
                    )
                )
            except Exception:
                pass
        app.logger.warning("schema_compat: created ai_coaching_notes table")
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
    """Create playbook tables/columns with raw SQL (no MetaData FK to users)."""
    from app import db

    try:
        insp = sa.inspect(db.engine)
        dialect = _dialect_name(db.engine)

        if not insp.has_table("playbook_setups"):
            if dialect == "postgresql":
                ddl = """
                CREATE TABLE IF NOT EXISTS playbook_setups (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(140) NOT NULL DEFAULT '',
                    market VARCHAR(40) NOT NULL DEFAULT '',
                    symbol_hint VARCHAR(40) NOT NULL DEFAULT '',
                    timeframe VARCHAR(16) NOT NULL DEFAULT '',
                    entry_criteria TEXT NOT NULL DEFAULT '',
                    invalidation TEXT NOT NULL DEFAULT '',
                    management_plan TEXT NOT NULL DEFAULT '',
                    checklist_text TEXT NOT NULL DEFAULT '',
                    tags VARCHAR(180) NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    example_images TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NULL
                )
                """
            else:
                ddl = """
                CREATE TABLE IF NOT EXISTS playbook_setups (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(140) NOT NULL DEFAULT '',
                    market VARCHAR(40) NOT NULL DEFAULT '',
                    symbol_hint VARCHAR(40) NOT NULL DEFAULT '',
                    timeframe VARCHAR(16) NOT NULL DEFAULT '',
                    entry_criteria TEXT NOT NULL DEFAULT '',
                    invalidation TEXT NOT NULL DEFAULT '',
                    management_plan TEXT NOT NULL DEFAULT '',
                    checklist_text TEXT NOT NULL DEFAULT '',
                    tags VARCHAR(180) NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    example_images TEXT NOT NULL DEFAULT '[]',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            with db.engine.begin() as conn:
                conn.execute(sa.text(ddl))
                try:
                    conn.execute(
                        sa.text(
                            "CREATE INDEX IF NOT EXISTS ix_playbook_setups_user_id "
                            "ON playbook_setups (user_id)"
                        )
                    )
                except Exception:
                    pass
            app.logger.warning("schema_compat: created playbook_setups table")
        else:
            pb_cols = {c.get("name") for c in insp.get_columns("playbook_setups")}
            if "example_images" not in pb_cols:
                with db.engine.begin() as conn:
                    conn.execute(
                        sa.text(
                            _add_column_sql(dialect, "playbook_setups", "example_images", "TEXT", "'[]'")
                        )
                    )
                app.logger.warning("schema_compat: added playbook_setups.example_images")

        _clear_insp(insp)
        insp = sa.inspect(db.engine)
        if insp.has_table("trades"):
            trade_cols = {c.get("name") for c in insp.get_columns("trades")}
            if "playbook_setup_id" not in trade_cols:
                with db.engine.begin() as conn:
                    conn.execute(
                        sa.text(_add_column_sql(dialect, "trades", "playbook_setup_id", "INTEGER", None))
                    )
                    try:
                        conn.execute(
                            sa.text(
                                "CREATE INDEX IF NOT EXISTS ix_trades_playbook_setup_id "
                                "ON trades (playbook_setup_id)"
                            )
                        )
                    except Exception:
                        pass
                app.logger.warning("schema_compat: added trades.playbook_setup_id")

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


def repair_alembic_version(app: Any) -> None:
    """
    If the DB already has ``users`` but Alembic thinks we are at the beginning
    (empty / early revisions), stamp to the current head so boots stop replaying
    ``initial schema`` forever.
    """
    from app import db

    try:
        insp = sa.inspect(db.engine)
        if not insp.has_table("users"):
            return

        versions: list[str] = []
        if insp.has_table("alembic_version"):
            with db.engine.connect() as conn:
                rows = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
                versions = [str(r[0]) for r in rows if r and r[0]]

        needs_stamp = False
        if not versions:
            needs_stamp = True
        elif all(v in _EARLY_ALEMBIC_REVS for v in versions) and _TARGET_ALEMBIC_REV not in versions:
            # Stuck on early branched heads from empty-version upgrades
            needs_stamp = True
        elif len(versions) > 1 and _TARGET_ALEMBIC_REV not in versions:
            needs_stamp = True

        if not needs_stamp:
            return

        app.logger.warning(
            "schema_compat: repairing alembic_version %s -> %s",
            versions or ["<empty>"],
            _TARGET_ALEMBIC_REV,
        )
        with db.engine.begin() as conn:
            if not insp.has_table("alembic_version"):
                conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
            conn.execute(sa.text("DELETE FROM alembic_version"))
            conn.execute(
                sa.text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": _TARGET_ALEMBIC_REV},
            )
        try:
            db.session.rollback()
        except Exception:
            pass
    except Exception as exc:
        app.logger.warning("schema_compat: repair_alembic_version failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


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
        "ai_coaching_ready": False,
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
                "schema_compat: users still missing columns %s after ensure",
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
