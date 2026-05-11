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
        has_setup_col = "playbook_setup_id" in ({c.get("name") for c in insp.get_columns("trades")} if insp.has_table("trades") else set())

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
