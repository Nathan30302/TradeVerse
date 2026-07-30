"""
Smart instrument/session/weekday comparisons from journal evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


def build_smart_comparisons(user_id: int, *, last_n: int = 60) -> Dict[str, Any]:
    """Compare instruments, sessions, weekdays, setups — evidence only."""
    from app.models.trade import Trade

    try:
        trades = (
            Trade.query.filter(
                Trade.user_id == int(user_id),
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(int(last_n))
            .all()
        )
    except Exception:
        trades = []

    empty = {"has_data": False, "insights": [], "groups": {}}
    if len(trades) < 4:
        return empty

    def bucket(key_fn) -> List[Dict[str, Any]]:
        groups: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            k = key_fn(t)
            if not k:
                continue
            groups[str(k)].append(float(t.profit_loss or 0))
        rows = []
        for name, pnls in groups.items():
            if len(pnls) < 2:
                continue
            wins = sum(1 for x in pnls if x > 0)
            rows.append(
                {
                    "name": name,
                    "trades": len(pnls),
                    "win_rate": round(wins / len(pnls) * 100, 1),
                    "net": round(sum(pnls), 2),
                }
            )
        rows.sort(key=lambda r: (r["net"], r["win_rate"]), reverse=True)
        return rows

    by_symbol = bucket(lambda t: (t.symbol or "").upper() or None)
    by_session = bucket(lambda t: t.session_type or None)
    by_strategy = bucket(lambda t: t.strategy or None)

    def by_weekday():
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        groups: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            d = t.exit_date or t.entry_date
            if not d:
                continue
            groups[names[d.weekday()]].append(float(t.profit_loss or 0))
        rows = []
        for name, pnls in groups.items():
            if len(pnls) < 2:
                continue
            wins = sum(1 for x in pnls if x > 0)
            rows.append(
                {
                    "name": name,
                    "trades": len(pnls),
                    "win_rate": round(wins / len(pnls) * 100, 1),
                    "net": round(sum(pnls), 2),
                }
            )
        rows.sort(key=lambda r: (r["net"], r["win_rate"]), reverse=True)
        return rows

    weekday = by_weekday()
    insights: List[str] = []

    def contrast(rows: List[Dict[str, Any]], label: str) -> None:
        if len(rows) < 2:
            return
        best, worst = rows[0], rows[-1]
        if best["name"] == worst["name"]:
            return
        if best["net"] > worst["net"]:
            insights.append(
                f"You perform better on {label} **{best['name']}** "
                f"({best['win_rate']:.0f}% WR, net {best['net']:+.2f}) than "
                f"**{worst['name']}** ({worst['win_rate']:.0f}% WR, net {worst['net']:+.2f})."
            )

    contrast(by_symbol, "instrument")
    contrast(by_session, "session")
    contrast(weekday, "weekday")
    contrast(by_strategy, "setup")

    # Morning vs afternoon if entry hour available
    am, pm = [], []
    for t in trades:
        d = t.entry_date
        if not d:
            continue
        hour = d.hour
        pnl = float(t.profit_loss or 0)
        if hour < 12:
            am.append(pnl)
        else:
            pm.append(pnl)
    if len(am) >= 2 and len(pm) >= 2:
        am_net, pm_net = sum(am), sum(pm)
        am_wr = sum(1 for x in am if x > 0) / len(am) * 100
        pm_wr = sum(1 for x in pm if x > 0) / len(pm) * 100
        if am_net != pm_net:
            better = "morning" if am_net > pm_net else "afternoon"
            insights.append(
                f"Your {better} trades are stronger "
                f"(AM net {am_net:+.2f} / {am_wr:.0f}% WR vs PM net {pm_net:+.2f} / {pm_wr:.0f}% WR)."
            )

    return {
        "has_data": True,
        "insights": insights[:6],
        "groups": {
            "instruments": by_symbol[:5],
            "sessions": by_session[:5],
            "weekdays": weekday[:7],
            "setups": by_strategy[:5],
        },
        "sample_size": len(trades),
    }
