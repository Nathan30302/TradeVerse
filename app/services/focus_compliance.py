"""
Weekly focus compliance — close the Trade Doctor → rule → next N trades loop.

Scores closed trades since the focus was set using lightweight heuristics so
AI Buddy can say “you followed your rule 8/10 times” without NLP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.trade import Trade


def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
        return default


def _rule_text(user) -> str:
    return (_safe_getattr(user, "weekly_focus_rule", None) or "").strip()


def _focus_since(user) -> Optional[datetime]:
    raw = _safe_getattr(user, "weekly_focus_set_at", None)
    if not raw:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is not None:
            return raw.astimezone(timezone.utc).replace(tzinfo=None)
        return raw
    return None


def _trade_day_key(trade: Trade) -> str:
    d = trade.entry_date or trade.exit_date
    if not d:
        return ""
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(d)[:10]


def trade_follows_focus(trade: Trade, focus_rule: str) -> Tuple[bool, List[str]]:
    """
    Heuristic: did this closed trade respect the weekly focus rule?

    Returns (followed, reasons) — reasons list failed checks when followed is False.
    """
    rule = (focus_rule or "").lower()
    if not rule:
        return True, []

    fails: List[str] = []
    checks_run = 0

    mentions_sl = any(k in rule for k in ("sl", "stop", "risk", "r:r", "rr", "1:1"))
    mentions_playbook = any(k in rule for k in ("playbook", "a+", "setup", "checklist", "system"))
    mentions_tag = any(k in rule for k in ("tag", "strategy", "journal"))
    mentions_revenge = any(k in rule for k in ("revenge", "fomo", "emotion", "break", "cooldown", "after any loss"))
    mentions_max = any(k in rule for k in ("max 2", "2 trades", "two trades", "per day", "daily"))
    mentions_doctor = "trade doctor" in rule or rule.startswith("address this week")

    if mentions_sl or mentions_doctor:
        checks_run += 1
        has_risk = bool(getattr(trade, "stop_loss", None) is not None or getattr(trade, "risk_amount", None))
        if not has_risk:
            fails.append("missing SL/risk")

    if mentions_playbook:
        checks_run += 1
        if not bool(getattr(trade, "playbook_followed", False)):
            fails.append("playbook not followed")

    if mentions_tag or mentions_doctor:
        checks_run += 1
        if not (getattr(trade, "strategy", None) or "").strip():
            fails.append("missing strategy tag")

    if mentions_revenge:
        checks_run += 1
        emo = (getattr(trade, "emotion", None) or "").strip().lower()
        bad = ("revenge", "fomo", "angry", "tilt", "impulsive", "anxious")
        if emo and any(b in emo for b in bad):
            fails.append(f"emotion={emo}")

    # Default structure bar when rule is generic
    if checks_run == 0:
        checks_run = 2
        has_risk = bool(getattr(trade, "stop_loss", None) is not None or getattr(trade, "risk_amount", None))
        has_tag = bool((getattr(trade, "strategy", None) or "").strip())
        if not has_risk:
            fails.append("missing SL/risk")
        if not has_tag:
            fails.append("missing strategy tag")

    # Max-trades/day is evaluated at series level in measure_focus_compliance
    _ = mentions_max

    return (len(fails) == 0), fails


def measure_focus_compliance(user, *, last_n: int = 10) -> Dict[str, Any]:
    """
    Score closed trades since weekly focus was set (capped at last_n).

    If focus_set_at is missing, uses the most recent last_n closed trades
    only when a focus rule exists (so older accounts still get a signal).
    """
    rule = _rule_text(user)
    empty = {
        "has_focus": bool(rule),
        "focus_rule": rule,
        "since": None,
        "sample_size": 0,
        "followed": 0,
        "broken": 0,
        "rate": None,
        "label": "No weekly focus set",
        "detail": "Set a weekly focus from Trade Doctor or AI Buddy.",
        "trades": [],
        "max_day_ok": True,
    }
    if not rule:
        return empty

    since = _focus_since(user)
    uid = getattr(user, "id", None)
    if not uid:
        return empty

    try:
        q = Trade.query.filter(
            Trade.user_id == uid,
            Trade.status == "CLOSED",
            Trade.profit_loss.isnot(None),
        )
        if since is not None:
            q = q.filter(
                (Trade.exit_date >= since) | ((Trade.exit_date.is_(None)) & (Trade.entry_date >= since))
            )
        trades = q.order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc()).limit(int(last_n)).all()
        trades = list(reversed(trades))  # chronological for day-cap checks
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
        trades = []

    if not trades:
        out = dict(empty)
        out["label"] = "Focus set — waiting for trades"
        out["detail"] = "Compliance unlocks after you close trades under this rule."
        out["since"] = since.isoformat() if since else None
        return out

    rule_l = rule.lower()
    mentions_max = any(k in rule_l for k in ("max 2", "2 trades", "two trades", "per day"))
    day_counts: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    followed = 0
    broken = 0
    max_day_ok = True

    for t in trades:
        ok, fails = trade_follows_focus(t, rule)
        day = _trade_day_key(t)
        if day:
            day_counts[day] = day_counts.get(day, 0) + 1
            if mentions_max and day_counts[day] > 2:
                ok = False
                fails = list(fails) + ["over daily max"]
                max_day_ok = False
        if ok:
            followed += 1
        else:
            broken += 1
        rows.append(
            {
                "id": t.id,
                "symbol": t.symbol or "?",
                "pnl": float(t.profit_loss or 0),
                "followed": ok,
                "fails": fails,
            }
        )

    n = followed + broken
    rate = (followed / n * 100.0) if n else None
    if rate is None:
        label = "No sample yet"
        detail = "Close trades to measure adherence."
    elif rate >= 80:
        label = f"Strong adherence · {followed}/{n}"
        detail = f"You followed your focus on {followed} of the last {n} closed trades."
    elif rate >= 50:
        label = f"Mixed · {followed}/{n}"
        detail = f"Followed {followed}/{n}. Tighten the rule before sizing up."
    else:
        label = f"Broken often · {followed}/{n}"
        detail = f"Only {followed}/{n} trades respected the focus — re-run Trade Doctor or simplify the rule."

    return {
        "has_focus": True,
        "focus_rule": rule,
        "since": since.isoformat() if since else None,
        "sample_size": n,
        "followed": followed,
        "broken": broken,
        "rate": round(rate, 1) if rate is not None else None,
        "label": label,
        "detail": detail,
        "trades": rows[-last_n:],
        "max_day_ok": max_day_ok,
    }


def build_post_close_coach_card(user, trade: Trade) -> Dict[str, Any]:
    """Structured coach moment shown right after a trade closes / on review."""
    pnl = float(getattr(trade, "profit_loss", None) or 0)
    sym = getattr(trade, "symbol", None) or "trade"
    emo = (getattr(trade, "emotion", None) or "").strip()
    note = (getattr(trade, "post_trade_notes", None) or getattr(trade, "lessons_learned", None) or "").strip()
    followed_pb = bool(getattr(trade, "playbook_followed", False))
    has_sl = getattr(trade, "stop_loss", None) is not None or getattr(trade, "risk_amount", None) is not None

    if pnl > 0:
        headline = f"Winner on {sym} ({pnl:+.2f})"
    elif pnl < 0:
        headline = f"Loss on {sym} ({pnl:+.2f})"
    else:
        headline = f"Closed {sym} breakeven"

    lessons: List[str] = []
    if not has_sl:
        lessons.append("No SL/risk logged — undefined risk is a silent account killer.")
    if not followed_pb and pnl < 0:
        lessons.append("Playbook not marked followed on a loser — was this off-system?")
    if emo and emo.lower() in ("revenge", "fomo", "angry", "tilt"):
        lessons.append(f"Emotion tagged {emo} — enforce a break before the next entry.")
    if note:
        lessons.append(note[:160] + ("…" if len(note) > 160 else ""))
    if not lessons:
        if pnl < 0:
            lessons.append("Add a one-line lesson now so AI Buddy can spot the pattern.")
        else:
            lessons.append("Solid close. Tag strategy + emotion so winners stay repeatable.")

    # Suggest a concrete next-week rule
    if not has_sl:
        suggested = "No SL / no risk = no trade. Size from invalidation only."
    elif emo and emo.lower() in ("revenge", "fomo", "angry", "tilt"):
        suggested = "After any loss: 15-minute break before the next entry."
    elif not followed_pb:
        suggested = "A+ playbook setups only for the next 10 trades."
    elif pnl < 0:
        suggested = "Max 2 trades per day; stop after 2 losses."
    else:
        suggested = "Keep tagging strategy + emotion; review only A+ setups this week."

    compliance = measure_focus_compliance(user, last_n=10)
    this_ok, this_fails = trade_follows_focus(trade, _rule_text(user))

    return {
        "headline": headline,
        "lesson": lessons[0],
        "lessons": lessons[:3],
        "suggested_rule": suggested,
        "trade_id": trade.id,
        "pnl": pnl,
        "emotion": emo,
        "playbook_followed": followed_pb,
        "has_risk": has_sl,
        "focus_followed": this_ok if _rule_text(user) else None,
        "focus_fails": this_fails,
        "compliance": compliance,
    }
