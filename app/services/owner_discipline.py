"""
Owner discipline coach — multi-strategy bible, session gates, risk, daily limits.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from app.services.entitlements import _safe_getattr, is_owner_user
from app.services.owner_strategy_seeds import FX_ALEXG_SLUG, fx_alexg_strategy_payload
from app.utils.timeutil import resolve_zoneinfo


WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def is_owner_discipline_user(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = (_safe_getattr(user, "role", None) or "").strip().lower()
    return role == "owner" or is_owner_user(user)


def get_or_create_rulebook(user):
    from app import db
    from app.models.owner_rules import OwnerRulebook

    book = OwnerRulebook.query.filter_by(user_id=user.id).first()
    if book:
        ensure_seeded_strategies(user, book)
        return book
    book = OwnerRulebook(
        user_id=user.id,
        strategy_name="Owner desk",
        session_windows_json="[]",
        gate_strict=True,
        enabled=True,
        risk_base_pct=1.0,
        risk_min_pct=0.25,
        trades_today=0,
        wins_today=0,
        losses_today=0,
        day_locked=False,
    )
    db.session.add(book)
    db.session.commit()
    ensure_seeded_strategies(user, book)
    return book


def ensure_seeded_strategies(user, book=None):
    """Ensure Strategy 1 (FX AlexG) exists. Does not overwrite personal edits."""
    from app import db
    from app.models.owner_rules import OwnerStrategy

    payload = fx_alexg_strategy_payload()
    existing = OwnerStrategy.query.filter_by(user_id=user.id, slug=payload["slug"]).first()
    if not existing:
        existing = OwnerStrategy(user_id=user.id, slug=payload["slug"])
        _apply_payload(existing, payload)
        existing.sort_order = 1
        db.session.add(existing)
        db.session.flush()
    if book is None:
        book = OwnerRulebook_for(user)
    if book and not book.active_strategy_id:
        book.active_strategy_id = existing.id
        book.session_windows_json = existing.session_windows_json
        book.gate_strict = bool(existing.gate_strict)
        book.max_trades_per_day = existing.max_trades_per_day
        book.risk_base_pct = existing.risk_base_pct
        book.risk_min_pct = existing.risk_min_pct
        book.strategy_name = existing.name
    db.session.commit()
    return existing


def OwnerRulebook_for(user):
    from app.models.owner_rules import OwnerRulebook

    return OwnerRulebook.query.filter_by(user_id=user.id).first()


def _apply_payload(row, payload: Dict[str, Any]) -> None:
    row.name = payload["name"]
    row.tagline = payload.get("tagline")
    row.style = payload.get("style")
    row.overview = payload.get("overview")
    row.markets = payload.get("markets")
    row.instruments_json = json.dumps(payload.get("instruments") or [])
    row.timeframes = payload.get("timeframes")
    row.timezone_name = payload.get("timezone_name") or "America/New_York"
    row.weekly_bias_rules = payload.get("weekly_bias_rules")
    row.daily_bias_rules = payload.get("daily_bias_rules")
    row.h4_rules = payload.get("h4_rules")
    row.m15_rules = payload.get("m15_rules")
    row.entry_rules = payload.get("entry_rules")
    row.exit_rules = payload.get("exit_rules")
    row.invalidation_rules = payload.get("invalidation_rules")
    row.do_not_trade_rules = payload.get("do_not_trade_rules")
    row.psychology_rules = payload.get("psychology_rules")
    row.session_windows_json = json.dumps(payload.get("session_windows") or [])
    row.checklist_json = json.dumps(payload.get("checklist") or {})
    row.spec_json = json.dumps(payload.get("spec") or {})
    row.gate_strict = bool(payload.get("gate_strict", True))
    row.enabled = True
    row.stop_after_first_win = bool(payload.get("stop_after_first_win", True))
    row.max_trades_per_day = int(payload.get("max_trades_per_day") or 2)
    row.max_losses_in_row = payload.get("max_losses_in_row")
    row.risk_base_pct = float(payload.get("risk_base_pct") or 1.0)
    row.risk_min_pct = float(payload.get("risk_min_pct") or 0.25)
    row.min_rr = float(payload.get("min_rr") or 2.0)
    row.target_rr = float(payload.get("target_rr") or 4.0)


def list_strategies(user) -> List[Any]:
    from app.models.owner_rules import OwnerStrategy

    get_or_create_rulebook(user)
    return (
        OwnerStrategy.query.filter_by(user_id=user.id, enabled=True)
        .order_by(OwnerStrategy.sort_order.asc(), OwnerStrategy.id.asc())
        .all()
    )


def get_active_strategy(user, book=None):
    from app.models.owner_rules import OwnerStrategy

    book = book or get_or_create_rulebook(user)
    # Unit-test / advisory books may be SimpleNamespace without ORM ids.
    if not hasattr(book, "active_strategy_id") and not hasattr(book, "query"):
        return None
    try:
        sid = getattr(book, "active_strategy_id", None)
        if sid:
            s = OwnerStrategy.query.filter_by(id=sid, user_id=user.id).first()
            if s:
                return s
        strategies = list_strategies(user)
        return strategies[0] if strategies else None
    except Exception:
        return None


def set_active_strategy(user, strategy_id: int):
    from app import db
    from app.models.owner_rules import OwnerStrategy

    book = get_or_create_rulebook(user)
    s = OwnerStrategy.query.filter_by(id=strategy_id, user_id=user.id).first()
    if not s:
        return None
    book.active_strategy_id = s.id
    book.session_windows_json = s.session_windows_json
    book.gate_strict = bool(s.gate_strict)
    book.max_trades_per_day = s.max_trades_per_day
    book.risk_base_pct = s.risk_base_pct
    book.risk_min_pct = s.risk_min_pct
    book.strategy_name = s.name
    db.session.commit()
    return s


def parse_windows(source) -> List[Dict[str, Any]]:
    raw_json = getattr(source, "session_windows_json", None) or "[]"
    try:
        raw = json.loads(raw_json)
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


def _strategy_tz(strategy, user):
    name = (getattr(strategy, "timezone_name", None) or getattr(user, "timezone", None) or "America/New_York")
    return resolve_zoneinfo(name)


def _now_for_strategy(user, strategy=None) -> datetime:
    tz = (
        _strategy_tz(strategy, user)
        if strategy
        else resolve_zoneinfo(getattr(user, "timezone", None) or "UTC")
    )
    return datetime.now(tz)


def _refresh_day_counters(user, book, strategy=None) -> None:
    if not hasattr(book, "day_key"):
        return
    try:
        from app import db
    except Exception:
        return

    strategy = strategy or get_active_strategy(user, book)
    now = _now_for_strategy(user, strategy)
    today = now.date().isoformat()
    if book.day_key != today:
        book.day_key = today
        book.trades_today = 0
        book.wins_today = 0
        book.losses_today = 0
        book.day_locked = False
        book.day_lock_reason = None
        try:
            db.session.commit()
        except Exception:
            pass


def daily_trade_status(user, book=None, strategy=None) -> Dict[str, Any]:
    book = book or get_or_create_rulebook(user)
    strategy = strategy or get_active_strategy(user, book)
    _refresh_day_counters(user, book, strategy)
    max_trades = int(
        getattr(strategy, "max_trades_per_day", None)
        or getattr(book, "max_trades_per_day", None)
        or 2
    )
    stop_win = bool(getattr(strategy, "stop_after_first_win", True)) if strategy else True
    trades = int(getattr(book, "trades_today", 0) or 0)
    wins = int(getattr(book, "wins_today", 0) or 0)
    losses = int(getattr(book, "losses_today", 0) or 0)
    locked = bool(getattr(book, "day_locked", False))
    reason = getattr(book, "day_lock_reason", None)
    if not locked:
        if stop_win and wins >= 1:
            locked = True
            reason = "First trade won — done for the day (strategy rule)."
        elif trades >= max_trades:
            locked = True
            reason = f"Max {max_trades} trades reached for today."
        elif losses >= max_trades:
            locked = True
            reason = "Loss budget for today is used."
    return {
        "day_key": getattr(book, "day_key", None),
        "trades_today": trades,
        "wins_today": wins,
        "losses_today": losses,
        "max_trades": max_trades,
        "stop_after_first_win": stop_win,
        "locked": locked,
        "reason": reason,
        "remaining": max(0, max_trades - trades) if not locked else 0,
    }


def record_day_trade_result(user, result: str) -> Dict[str, Any]:
    """result: win | loss | scratch"""
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    book = get_or_create_rulebook(user)
    strategy = get_active_strategy(user, book)
    _refresh_day_counters(user, book, strategy)
    result = (result or "").strip().lower()
    book.trades_today = int(book.trades_today or 0) + 1
    if result == "win":
        book.wins_today = int(book.wins_today or 0) + 1
    elif result == "loss":
        book.losses_today = int(book.losses_today or 0) + 1
    status = daily_trade_status(user, book, strategy)
    if status["locked"]:
        book.day_locked = True
        book.day_lock_reason = status["reason"]
    db.session.add(
        OwnerRuleCheckLog(
            user_id=user.id,
            event_type="day_trade_result",
            detail=f"{result}; trades={book.trades_today}; wins={book.wins_today}; losses={book.losses_today}",
        )
    )
    db.session.commit()
    return daily_trade_status(user, book, strategy)


def session_gate(user, book=None, strategy=None) -> Dict[str, Any]:
    book = book or get_or_create_rulebook(user)
    if strategy is None:
        try:
            strategy = get_active_strategy(user, book)
        except Exception:
            strategy = None
    source = strategy or book
    now = _now_for_strategy(user, strategy)
    today = now.date().isoformat()
    windows = parse_windows(source)
    day = daily_trade_status(user, book, strategy)

    if not getattr(book, "enabled", True) or (strategy and not getattr(strategy, "enabled", True)):
        return {
            "allowed": True,
            "reason": "Rule system paused",
            "in_window": True,
            "active_window": None,
            "next_window": None,
            "unlocked": False,
            "local_time": now.strftime("%Y-%m-%d %H:%M"),
            "weekday": WEEKDAY_NAMES[now.weekday()],
            "day": day,
            "strategy_name": getattr(strategy, "name", None) or getattr(book, "strategy_name", None),
        }

    unlocked = (getattr(book, "unlocked_date", None) or "") == today
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
    strict = bool(
        getattr(strategy, "gate_strict", None)
        if strategy is not None
        else getattr(book, "gate_strict", True)
    )
    allowed = (in_window or unlocked or not strict) and not day["locked"]

    if day["locked"]:
        reason = day["reason"] or "Daily trade limit reached"
    elif in_window:
        reason = f"Inside {active['label']} ({active['start']}–{active['end']})"
    elif unlocked:
        reason = f"Session unlocked today — {getattr(book, 'unlocked_note', None) or 'manual open'}"
    elif not strict:
        reason = "Gate is advisory only (strict mode off)"
    else:
        reason = "Outside trading window — unlock or wait for the next session."

    return {
        "allowed": allowed,
        "reason": reason,
        "in_window": in_window,
        "active_window": active["label"] if active else None,
        "next_window": next_window,
        "unlocked": unlocked,
        "local_time": now.strftime("%Y-%m-%d %H:%M %Z"),
        "weekday": WEEKDAY_NAMES[now.weekday()],
        "strict": strict,
        "day": day,
        "strategy_name": getattr(strategy, "name", None) or getattr(book, "strategy_name", None),
        "timezone": getattr(strategy, "timezone_name", None) or "America/New_York",
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
    hwm = float(book.account_high_water or book.account_starting_balance or 0) or 0.0
    cur = float(book.account_current_balance or hwm or 0) or 0.0
    if hwm <= 0 or cur >= hwm:
        return 0.0
    return max(0.0, min(1.0, (hwm - cur) / hwm))


def suggested_risk(book, strategy=None) -> Dict[str, Any]:
    base = float(getattr(strategy, "risk_base_pct", None) or book.risk_base_pct or 1.0)
    floor = float(getattr(strategy, "risk_min_pct", None) or book.risk_min_pct or 0.25)
    if floor > base:
        floor = base
    dd = drawdown_fraction(book)
    scale = 1.0 - min(dd / 0.25, 1.0)
    risk_pct = floor + (base - floor) * scale
    balance = float(book.account_current_balance or book.account_starting_balance or 0) or 0.0
    risk_cash = balance * (risk_pct / 100.0) if balance else None
    if dd >= 0.20:
        mode = "recovery"
        advice = "Deep drawdown — floor risk only, A+ setups, stop after one loss today."
    elif dd >= 0.08:
        mode = "cautious"
        advice = "Off high-water — cut size and skip marginal AOIs."
    else:
        mode = "normal"
        advice = "Near high-water — use base risk only when the full checklist is green."
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


def calc_lot_size(
    *,
    balance: float,
    risk_pct: float,
    sl_pips: float,
    pip_value: float = 10.0,
) -> Dict[str, Any]:
    """Lot = (Balance × Risk%) / (SL_pips × pip_value). Default pip_value ≈ $10/pip on 1.0 FX lot."""
    if balance <= 0 or risk_pct <= 0 or sl_pips <= 0 or pip_value <= 0:
        return {"lots": None, "risk_cash": None, "error": "Need balance, risk %, SL pips, and pip value > 0."}
    risk_cash = balance * (risk_pct / 100.0)
    lots = risk_cash / (sl_pips * pip_value)
    return {
        "lots": round(lots, 2),
        "risk_cash": round(risk_cash, 2),
        "error": None,
        "formula": "Balance × Risk% / (SL pips × pip value)",
    }


def checklist_for(strategy) -> Dict[str, Any]:
    try:
        data = json.loads(strategy.checklist_json or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def build_multi_tf_brief(book, gate=None, strategy=None) -> Dict[str, Any]:
    strategy = strategy or get_active_strategy(None)  # noqa — fixed below
    return _brief(book, gate, strategy)


def _brief(book, gate, strategy) -> Dict[str, Any]:
    src = strategy or book
    frames = [
        {"key": "weekly", "label": "Weekly", "prompt": "Bodies only · HH/HL or LL/LH · Snake Trick", "rules": (src.weekly_bias_rules or "").strip()},
        {"key": "daily", "label": "Daily", "prompt": "Sync with Weekly or set up Daily+4H bridge", "rules": (src.daily_bias_rules or "").strip()},
        {"key": "h4", "label": "4 Hour", "prompt": "Confirm alignment — no conflicting bias", "rules": (src.h4_rules or "").strip()},
        {"key": "m15", "label": "15M–2H entry", "prompt": "Only after AOI + pattern", "rules": (src.m15_rules or "").strip()},
    ]
    missing = [f["label"] for f in frames if not f["rules"]]
    risk = suggested_risk(book, strategy)
    gate = gate or {}
    tips: List[str] = []
    day = (gate.get("day") or {})
    if day.get("locked"):
        tips.append(day.get("reason") or "Daily limit reached — protect the edge.")
    if not gate.get("in_window") and gate.get("strict"):
        tips.append("Outside the AlexG window (01:00–10:30 EST). Do not force entries.")
    if risk["mode"] != "normal":
        tips.append(risk["advice"])
    if (src.do_not_trade_rules or "").strip():
        tips.append("Re-read Do-Not-Trade before any order.")
    if not tips:
        tips.append("Checklist first — every green box, then market execution only.")
    return {
        "strategy_name": getattr(src, "name", None) or book.strategy_name,
        "tagline": getattr(src, "tagline", None),
        "style": getattr(src, "style", None),
        "overview": src.overview,
        "frames": frames,
        "entry_rules": (src.entry_rules or "").strip(),
        "exit_rules": (src.exit_rules or "").strip(),
        "invalidation_rules": (src.invalidation_rules or "").strip(),
        "do_not_trade": (src.do_not_trade_rules or "").strip(),
        "psychology": (src.psychology_rules or "").strip(),
        "tips": tips,
        "risk": risk,
        "completeness": round(100 * (4 - len(missing)) / 4, 0),
        "checklist": checklist_for(src) if strategy else {},
        "instruments": json.loads(getattr(src, "instruments_json", None) or "[]") if strategy else [],
        "min_rr": float(getattr(src, "min_rr", 2) or 2),
        "target_rr": float(getattr(src, "target_rr", 4) or 4),
    }


def build_desk_brief(user) -> Dict[str, Any]:
    book = get_or_create_rulebook(user)
    strategy = get_active_strategy(user, book)
    gate = session_gate(user, book, strategy)
    return _brief(book, gate, strategy)


# Fix accidental API: rebuild public alias used by routes
def build_multi_tf_brief_safe(book, gate=None, strategy=None) -> Dict[str, Any]:
    return _brief(book, gate, strategy)


def advise_before_trade(book, *, symbol: str = "", thesis: str = "", session_hint: str = "", strategy=None) -> Dict[str, Any]:
    strategy = strategy or None
    src = strategy or book
    warnings: List[str] = []
    ok_signals: List[str] = []
    thesis_l = (thesis or "").lower()
    dnt = (src.do_not_trade_rules or "").lower()
    instruments = []
    if strategy and strategy.instruments_json:
        try:
            instruments = [str(x).upper() for x in json.loads(strategy.instruments_json)]
        except (TypeError, json.JSONDecodeError):
            instruments = []
    if symbol and instruments and symbol.upper() not in instruments:
        warnings.append(f"{symbol} is not on this strategy’s approved instrument list.")
    revenge_words = ("revenge", "make it back", "all in", "double size", "fomo")
    if any(w in thesis_l for w in revenge_words):
        warnings.append("Emotional / revenge language — violates psychology rules.")
    if dnt:
        for chunk in re.split(r"[;\n•]+", dnt):
            chunk = chunk.strip()
            if len(chunk) >= 8 and chunk[:48].lower() in thesis_l:
                warnings.append(f"Conflicts with Do-Not-Trade: “{chunk[:80]}”")
    if not thesis_l:
        warnings.append("No thesis — AlexG requires confluence written before entry.")
    else:
        ok_signals.append("Thesis captured — confirm HTF sync + AOI + candle signal.")
    risk = suggested_risk(book, strategy)
    if risk["mode"] == "recovery":
        warnings.append(f"Recovery mode: max risk ≈ {risk['risk_pct']}%.")
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
        return "Do not trade. Protect capital and wait for the next A+ window."
    if verdict == "caution":
        return "Pause — resolve: " + "; ".join(warnings[:3])
    return "Aligned enough to continue the checklist — still confirm every state."


def unlock_session_today(user, book, note: str = "") -> None:
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    strategy = get_active_strategy(user, book)
    today = _now_for_strategy(user, strategy).date().isoformat()
    book.unlocked_date = today
    book.unlocked_note = (note or "Opened from Rules Desk")[:255]
    db.session.add(
        OwnerRuleCheckLog(user_id=user.id, event_type="unlocked_session", detail=book.unlocked_note)
    )
    db.session.commit()


def log_blocked_trade(user, detail: str) -> None:
    from app import db
    from app.models.owner_rules import OwnerRuleCheckLog

    db.session.add(
        OwnerRuleCheckLog(user_id=user.id, event_type="blocked_outside_hours", detail=(detail or "")[:2000])
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


def windows_as_text(source) -> str:
    lines = []
    for w in parse_windows(source):
        days = ",".join(str(d) for d in w["days"])
        lines.append(f"{w['label']}|{days}|{w['start']}|{w['end']}")
    return "\n".join(lines)


# Back-compat alias used by older routes/tests
build_multi_tf_brief = build_multi_tf_brief_safe  # type: ignore
