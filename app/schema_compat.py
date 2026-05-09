"""
Detect optional migrated schema (playbook / replay).

Lets the site run without the latest Alembic upgrades until the DB is migrated.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa


def refresh(app: Any) -> dict[str, bool]:
    """Populate app.extensions[\"tradeverse_schema\"] from the live database."""
    from app import db

    flags = {
        "playbook_ready": False,
        "replay_ready": False,
    }
    try:
        insp = sa.inspect(db.engine)
        has_pb = insp.has_table("playbook_setups")
        has_replay_tbl = insp.has_table("trade_replay_events")
        has_setup_col = False
        if insp.has_table("trades"):
            cols = {c.get("name") for c in insp.get_columns("trades")}
            has_setup_col = "playbook_setup_id" in cols
        flags["playbook_ready"] = bool(has_pb and has_setup_col)
        flags["replay_ready"] = bool(has_replay_tbl)
        app.extensions["tradeverse_schema"] = flags
    except Exception as exc:
        app.logger.warning("tradeverse_schema: inspection failed (%s); running without playbook/replay", exc)
        app.extensions["tradeverse_schema"] = flags
    return flags
