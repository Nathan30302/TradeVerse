"""
Advanced analytics engine (trader-grade metrics).

Focuses on metrics derivable from stored trade data:
- R-multiples (requires stop_loss or risk_amount)
- Expectancy in R
- Absolute + relative drawdown from closed trades equity curve
- Basic correlations by emotion/session/strategy

MAE/MFE require intratrade price series and are exposed as optional fields
for future enrichment (broker data / chart snapshots).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class EquityPoint:
    t: datetime
    equity: float
    trade_pnl: float
    r: Optional[float]


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def compute_r_multiple(trade) -> Optional[float]:
    """
    R multiple = PnL / risk_amount.

    Uses stored risk_amount when present, else derives a rough proxy from
    price distance to stop_loss * lot_size. (This is an approximation and will
    be replaced by instrument-aware risk calcs later.)
    """
    pnl = getattr(trade, "profit_loss", None)
    if pnl is None:
        return None

    risk_amount = getattr(trade, "risk_amount", None)
    if risk_amount and risk_amount > 0:
        return float(pnl) / float(risk_amount)

    entry = getattr(trade, "entry_price", None)
    sl = getattr(trade, "stop_loss", None)
    lot = getattr(trade, "lot_size", None)
    if entry is None or sl is None or lot is None:
        return None

    risk_proxy = abs(float(entry) - float(sl)) * float(lot)
    if risk_proxy <= 0:
        return None
    return float(pnl) / risk_proxy


def equity_curve_points(trades: Iterable) -> List[EquityPoint]:
    equity: float = 0.0
    out: List[EquityPoint] = []

    # assume trades already sorted by exit_date
    for t in trades:
        pnl = getattr(t, "profit_loss", None)
        exit_dt = getattr(t, "exit_date", None)
        if pnl is None or exit_dt is None:
            continue
        pnl_f = float(pnl)
        equity += pnl_f
        out.append(EquityPoint(t=exit_dt, equity=equity, trade_pnl=pnl_f, r=compute_r_multiple(t)))
    return out


def max_drawdown(points: List[EquityPoint]) -> Dict[str, float]:
    """
    Returns absolute and relative max drawdown.
    Relative is computed vs peak equity (avoid divide-by-zero).
    """
    peak = float("-inf")
    max_abs = 0.0
    max_rel = 0.0
    eq = 0.0

    for p in points:
        eq = p.equity
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_abs:
            max_abs = dd
        if peak > 0:
            max_rel = max(max_rel, dd / peak)

    return {"max_drawdown_abs": float(max_abs), "max_drawdown_rel": float(max_rel)}


def expectancy_r(points: List[EquityPoint]) -> Dict[str, float]:
    rs = [p.r for p in points if p.r is not None]
    if not rs:
        return {"expectancy_r": 0.0, "avg_r": 0.0, "win_rate": 0.0}
    wins = [r for r in rs if r > 0]
    win_rate = len(wins) / len(rs) if rs else 0.0
    avg_r = sum(rs) / len(rs)
    return {"expectancy_r": float(avg_r), "avg_r": float(avg_r), "win_rate": float(win_rate)}


def group_pnl(trades: Iterable, key_fn) -> List[Dict[str, object]]:
    buckets: Dict[str, Dict[str, object]] = {}
    for t in trades:
        pnl = getattr(t, "profit_loss", None)
        if pnl is None:
            continue
        k = key_fn(t) or "Unknown"
        k = str(k)
        b = buckets.setdefault(k, {"key": k, "count": 0, "total_pnl": 0.0, "wins": 0, "losses": 0})
        b["count"] = int(b["count"]) + 1
        b["total_pnl"] = float(b["total_pnl"]) + float(pnl)
        if float(pnl) > 0:
            b["wins"] = int(b["wins"]) + 1
        elif float(pnl) < 0:
            b["losses"] = int(b["losses"]) + 1
    out = list(buckets.values())
    out.sort(key=lambda x: float(x["total_pnl"]), reverse=True)
    return out

