"""
Owner discipline coach — enforce Nathan's written rules, time gates, and risk scaling.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.entitlements import _safe_getattr, is_owner_user
from app.utils.timeutil import resolve_zoneinfo, utc_now


WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def is_owner_discipline_user(user) -> bool:
    """Only the platform owner (role or allowlist) sees / uses this system."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = (_safe_getattr(user, "role", None) or "").strip().lower()
    return role == "owner" or is_owner_user(user)


def get_or_create_rulebook(user):
    from app import db
    from app.models.owner_rules import OwnerRulebook

    book = OwnerRulebook.query.filter_by(user_id=user.id).first()
    if book:
        return book
    book = OwnerRulebook(
        user_id=user.id,
        strategy_name="Nathan's system",
        session_windows_json=json.dumps(
            [
                {
                    "label": "London",
                    "days": [0, 1, 2, 3, 4],
                    "start": "07:00",
                    "end": "11:30",
                },
                {
                    "label": "New York open",
                    "days": [0, 1, 2, 3, 4],
                    "start": "13:30",
                    "end": "16:30",
                },
            ]
        ),
        timeframes="W, D, H4, M15",
        gate_strict=True,
        enabled=True,
        risk_base_pct=1.0,
        risk_min_pct=0.25,
    )
    db.session.add(book)
    db.session.commit()
    return book


def parse_windows(book) -> List[Dict[str, Any]]:
    try:
        raw = json.loads(book.session_windows_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    out = []
    for w in raw if isinstance(raw, list) else []:
        if not isinstance(w, dict):
            continue
        try:
            start = _parse_hhmm(w.get("start"))
            end = _parse_hhmm(w.get("end"))
            days = [int(d) for d in (w.get("days") or [])]
        except (TypeError, ValueError):
            continue
        if start is None or end is None:
            continue
        out.append(
            {
                "label": (w.get("label") or "Session").strip()[:60],
                "days": days,
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "_start": start,
                "_end": end,
            }
        )
    return out


def _parse_hhmm(value) -> Optional[time]:
    text = str(value or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return time(h, mi)


def _local_now(user) -> datetime:
    tz = resolve_zoneinfo(getattr(user, "timezone", None) or "UTC")
    return datetime.now(tz)


def session_gate(user, book=None) -> Dict[str, Any]:
    """
    Can Nathan trade right now?

    Outside configured windows → blocked unless unlocked_date == today (local)
    or gate_strict is off / system disabled.
    """
    book = book or get_or_create_rulebook(user)
    now = _local_now(user)
    today = now.date().isoformat()
    windows = parse_windows(book)

    if not book.enabled:
        return {
            "allowed": True,
            "reason": "Rule system paused",
            "in_window": True,
            "active_window": None,
            "next_window": None,
            "unlocked": False,
            "local_time": now.strftime("%Y-%m-%d %H:%M"),
            "weekday": WEEKDAY_NAMES[now.weekday()],
        }

    unlocked = (book.unlocked_date or "") == today
    active = None
    for w in windows:
        if now.weekday() not in w["days"]:
            continue
        start_dt = datetime.combine(now.date(), w["_start"], tzinfo=now.tzinfo)
        end_dt = datetime.combine(now.date(), w["_end"], tzinfo=now.tzinfo)
        if start_dt <= now <= end_dt:
            active = w
            break

    next_window = _next_window(now, windows)
    in_window = active is not None
    allowed = in_window or unlocked or (not book.gate_strict)

    if in_window:
        reason = f"Inside {active['label']} ({active['start']}–{active['end']})"
    elif unlocked:
        reason = f"Session unlocked today — {book.unlocked_note or 'manual open'}"
    elif not book.gate_strict:
        reason = "Gate is advisory only (strict mode off)"
    else:
        reason = "Outside your trading windows — open the Rules Desk to unlock, or wait."

    return {
        "allowed": allowed,
        "reason": reason,
        "in_window": in_window,
        "active_window": active["label"] if active else None,
        "next_window": next_window,
        "unlocked": unlocked,
        "local_time": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": WEEKDAY_NAMES[now.weekday()],
        "strict": bool(book.gate_strict),
    }


def _next_window(now: datetime, windows: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    candidates = []
    for offset in range(0, 8):
        day = now.date() + timedelta(days=offset)
        wd = day.weekday()
        for w in windows:
            if wd not in w["days"]:
                continue
            start_dt = datetime.combine(day, w["_start"], tzinfo=now.tzinfo)
            if start_dt > now:
                candidates.append((start_dt, w))
    if not candidates:
        return None
    start_dt, w = min(candidates, key=lambda x: x[0])
    return {
        "label": w["label"],
        "when": start_dt.strftime("%a %H:%M"),
        "start": w["start"],
        "end": w["end"],
    }


def drawdown_fraction(book) -> float:
    """0 = at/above high water; 0.2 = 20% off peak."""
    hwm = float(book.account_high_water or book.account_starting_balance or 0) or 0.0
    cur = float(book.account_current_balance or hwm or 0) or 0.0
    if hwm <= 0:
        return 0.0
    if cur >= hwm:
        return 0.0
    return max(0.0, min(1.0, (hwm - cur) / hwm))


def suggested_risk(book) -> Dict[str, Any]:
    """
    When equity falls from high-water, risk % steps down toward risk_min_pct.
    Helps climb out of drawdown instead of revenge-sizing.
    """
    base = float(book.risk_base_pct or 1.0)
    floor = float(book.risk_min_pct or 0.25)
    if floor > base:
        floor = base
    dd = drawdown_fraction(book)
    # Linear scale: 0% DD → base; 25%+ DD → floor
    scale = 1.0 - min(dd / 0.25, 1.0)
    risk_pct = floor + (base - floor) * scale
    balance = float(book.account_current_balance or book.account_starting_balance or 0) or 0.0
    risk_cash = balance * (risk_pct / 100.0) if balance else None

    if dd >= 0.20:
        mode = "recovery"
        advice = (
            "You are deep in drawdown. Cut size to the floor risk, trade only A+ setups "
            "from your written rules, and stop after one loss today."
        )
    elif dd >= 0.08:
        mode = "cautious"
        advice = (
            "Equity is off the high-water mark. Use reduced risk and skip marginal setups — "
            "protect the climb back."
        )
    else:
        mode = "normal"
        advice = "Near high-water — use base risk only when every timeframe filter on your bible is green."

    return {
        "mode": mode,
        "drawdown_pct": round(dd * 100, 2),
        "risk_pct": round(risk_pct, 3),
        "risk_cash": round(risk_cash, 2) if risk_cash is not None else None,
        "base_pct": base,
        "min_pct": floor,
        "balance": balance,
        "high_water": float(book.account_high_water or 0) or None,
        "advice": advice,
    }


def build_multi_tf_brief(book, gate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structure Nathan's written rules into a pre-trade intelligence brief."""
    frames = [
        {
            "key": "weekly",
            "label": "Weekly",
            "prompt": "What is this week's bias from your rules?",
            "rules": (book.weekly_bias_rules or "").strip(),
        },
        {
            "key": "daily",
            "label": "Daily",
            "prompt": "Does today align with weekly bias?",
            "rules": (book.daily_bias_rules or "").strip(),
        },
        {
            "key": "h4",
            "label": "4 Hour",
            "prompt": "Is H4 structure confirming the daily idea?",
            "rules": (book.h4_rules or "").strip(),
        },
        {
            "key": "m15",
            "label": "15 Minute",
            "prompt": "Wait for your M15 entry trigger only — no early click.",
            "rules": (book.m15_rules or "").strip(),
        },
    ]
    missing = [f["label"] for f in frames if not f["rules"]]
    risk = suggested_risk(book)
    gate = gate or {}

    tips: List[str] = []
    if not gate.get("in_window") and gate.get("strict"):
        tips.append("You are outside your allowed session. Do not force a trade.")
    if risk["mode"] != "normal":
        tips.append(risk["advice"])
    if (book.do_not_trade_rules or "").strip():
        tips.append("Re-read your Do-Not-Trade list before any order.")
    if missing:
        tips.append(
            "Fill missing timeframe rules in your bible so the desk can coach you properly: "
            + ", ".join(missing)
        )
    if not tips:
        tips.append("All systems set — only take the trade if every frame on your bible agrees.")

    return {
        "strategy_name": book.strategy_name,
        "overview": book.overview,
        "frames": frames,
        "entry_rules": (book.entry_rules or "").strip(),
        "exit_rules": (book.exit_rules or "").strip(),
        "invalidation_rules": (book.invalidation_rules or "").strip(),
        "do_not_trade": (book.do_not_trade_rules or "").strip(),
        "psychology": (book.psychology_rules or "").strip(),
        "tips": tips,
        "risk": risk,
        "completeness": round(100 * (4 - len(missing)) / 4, 0) if frames else 0,
    }


def advise_before_trade(book, *, symbol: str = "", thesis: str = "", session_hint: str = "") -> Dict[str, Any]:
    """Lightweight rule-check against Nathan's written bible."""
    warnings: List[str] = []
    ok_signals: List[str] = []
    thesis_l = (thesis or "").lower()
    dnt = (book.do_not_trade_rules or "").lower()
    entry = (book.entry_rules or "").lower()

    if getattr(book, "markets", None) and symbol:
        markets = book.markets.lower()
        sym = symbol.lower()
        if sym and sym not in markets and symbol.upper() not in (book.markets or ""):
            # soft check — only warn if markets list looks like a closed list
            if len((book.markets or "").split(",")) <= 12:
                warnings.append(f"{symbol} may be outside your allowed markets list.")

    # Keyword smells for common rule breaks
    revenge_words = ("revenge", "make it back", "all in", "double size", "fomo")
    if any(w in thesis_l for w in revenge_words):
        warnings.append("Language looks emotional / revenge — that breaks your psychology rules.")

    if dnt:
        for chunk in re.split(r"[;\n•]+", dnt):
            chunk = chunk.strip()
            if len(chunk) < 6:
                continue
            # If a do-not phrase appears in the thesis, warn
            key = chunk[:40].lower()
            if key and key in thesis_l:
                warnings.append(f"Conflicts with Do-Not-Trade: “{chunk[:80]}”")

    if entry and thesis_l:
        ok_signals.append("Thesis captured — confirm it matches your entry checklist below.")
    elif not thesis_l:
        warnings.append("No thesis yet. Your system requires a written why before entry.")

    if session_hint and "asia" in session_hint.lower() and "london" in (book.session_windows_json or "").lower():
        if "asia" not in (book.session_windows_json or "").lower():
            warnings.append("Asia session is not in your allowed windows.")

    risk = suggested_risk(book)
    if risk["mode"] == "recovery":
        warnings.append(f"Recovery mode: max risk ≈ {risk['risk_pct']}% of balance.")

    verdict = "hold"
    if warnings and risk["mode"] == "recovery":
        verdict = "no_trade"
    elif warnings:
        verdict = "caution"
    else:
        verdict = "aligned"

    return {
        "verdict": verdict,
        "warnings": warnings,
        "ok_signals": ok_signals,
        "suggested_risk_pct": risk["risk_pct"],
        "message": _verdict_message(verdict, warnings),
    }


def _verdict_message(verdict: str, warnings: List[str]) -> str:
    if verdict == "no_trade":
        return "Do not trade. Flatten your mindset, cut size, wait for the next A+ window."
    if verdict == "caution":
        return "Pause — resolve these rule flags before clicking buy/sell: " + "; ".join(warnings[:3])
    return "Looks aligned with your written system. Still confirm every timeframe filter."


def unlock_session_today(user, book, note: str = "") -> None:
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    today = _local_now(user).date().isoformat()
    book.unlocked_date = today
    book.unlocked_note = (note or "Opened from Rules Desk")[:255]
    db.session.add(
        OwnerRuleCheckLog(
            user_id=user.id,
            event_type="unlocked_session",
            detail=book.unlocked_note,
        )
    )
    db.session.commit()


def log_blocked_trade(user, detail: str) -> None:
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    db.session.add(
        OwnerRuleCheckLog(user_id=user.id, event_type="blocked_outside_hours", detail=detail[:2000])
    )
    db.session.commit()


def update_balance(book, current: float, *, bump_high_water: bool = True) -> Dict[str, Any]:
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    book.account_current_balance = float(current)
    if book.account_starting_balance is None:
        book.account_starting_balance = float(current)
    if bump_high_water:
        hwm = float(book.account_high_water or 0)
        if current > hwm:
            book.account_high_water = float(current)
    elif book.account_high_water is None:
        book.account_high_water = float(current)
    db.session.add(
        OwnerRuleCheckLog(
            user_id=book.user_id,
            event_type="balance_update",
            detail=f"balance={current}; hwm={book.account_high_water}",
        )
    )
    db.session.commit()
    return suggested_risk(book)


def windows_from_form(raw_text: str) -> str:
    """
    Parse lines like: London|0,1,2,3,4|07:00|11:30
    """
    windows = []
    for line in (raw_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        label, days_s, start, end = parts[0], parts[1], parts[2], parts[3]
        try:
            days = [int(x) for x in days_s.split(",") if x.strip() != ""]
        except ValueError:
            continue
        if _parse_hhmm(start) is None or _parse_hhmm(end) is None:
            continue
        windows.append({"label": label[:60], "days": days, "start": start, "end": end})
    return json.dumps(windows)


def windows_as_text(book) -> str:
    lines = []
    for w in parse_windows(book):
        days = ",".join(str(d) for d in w["days"])
        lines.append(f"{w['label']}|{days}|{w['start']}|{w['end']}")
    return "\n".join(lines)
