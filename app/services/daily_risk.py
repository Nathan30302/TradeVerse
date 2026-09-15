"""Daily risk lock: max loss in R and max trades per local day."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import load_only

from app import db
from app.models.trade import Trade
from app.services.analytics_engine import compute_r_multiple
from app.utils.timeutil import resolve_zoneinfo


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _user_day_bounds_utc(user) -> tuple:
    """Naive UTC [start, end) covering the user's local calendar day."""
    tz = resolve_zoneinfo(getattr(user, "timezone", None))
    now_local = datetime.now(timezone.utc).astimezone(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def get_daily_risk_snapshot(user) -> Dict[str, Any]:
    """
    Today's trade count and realized R vs optional user limits.

    Empty / unset limits mean the lock is off. ``locked`` is True only when a
    configured limit is reached or exceeded.
    """
    empty: Dict[str, Any] = {
        "enabled": False,
        "locked": False,
        "reasons": [],
        "trades_today": 0,
        "used_r": 0.0,
        "loss_limit_r": None,
        "max_trades": None,
        "label": "",
    }
    if user is None or not getattr(user, "id", None):
        return empty

    loss_limit = _safe_float(getattr(user, "daily_loss_limit_r", None))
    max_trades = _safe_int(getattr(user, "daily_max_trades", None))
    if loss_limit is not None and loss_limit <= 0:
        loss_limit = None
    if max_trades is not None and max_trades <= 0:
        max_trades = None

    enabled = bool(loss_limit or max_trades)
    start_utc, end_utc = _user_day_bounds_utc(user)

    trades_today = 0
    used_r = 0.0
    try:
        rows: List[Trade] = (
            Trade.query.filter(
                Trade.user_id == user.id,
                Trade.status != "CANCELLED",
                Trade.entry_date >= start_utc,
                Trade.entry_date < end_utc,
            )
            .options(
                load_only(
                    Trade.id,
                    Trade.status,
                    Trade.profit_loss,
                    Trade.risk_amount,
                    Trade.stop_loss,
                    Trade.entry_price,
                    Trade.lot_size,
                )
            )
            .all()
        )
        trades_today = len(rows)
        for trade in rows:
            if (trade.status or "").upper() != "CLOSED":
                continue
            r_mult = compute_r_multiple(trade)
            if r_mult is not None:
                used_r += float(r_mult)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        trades_today = 0
        used_r = 0.0

    reasons: List[str] = []
    if loss_limit is not None and used_r <= -abs(loss_limit):
        reasons.append(
            f"Daily loss limit reached ({used_r:+.1f}R of −{loss_limit:g}R)."
        )
    if max_trades is not None and trades_today >= max_trades:
        reasons.append(f"Daily trade limit reached ({trades_today} of {max_trades}).")

    locked = bool(reasons)
    parts = []
    if loss_limit is not None:
        parts.append(f"{used_r:+.1f}R of −{loss_limit:g}R")
    if max_trades is not None:
        parts.append(f"{trades_today} of {max_trades} trades")
    label = " · ".join(parts)

    return {
        "enabled": enabled,
        "locked": locked,
        "reasons": reasons,
        "trades_today": trades_today,
        "used_r": round(used_r, 2),
        "loss_limit_r": loss_limit,
        "max_trades": max_trades,
        "label": label,
    }


def daily_risk_blocks_new_trade(user) -> bool:
    """True when Add Trade should be refused (no override)."""
    snap = get_daily_risk_snapshot(user)
    return bool(snap.get("locked"))
