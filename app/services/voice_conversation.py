"""
Voice Journal conversation — the talk *is* the interface.

The model asks like a trading buddy, extracts a Trade-shaped draft after every
turn, and only reveals the structured log at the end. Regex parse is the
offline fallback when OpenAI is not configured.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from app.models.instrument import Instrument
from app.services.voice_journal import (
    normalize_symbol_guess,
    parse_voice_text,
    parse_yes_no,
    strategy_from_setups,
)


SYSTEM_PROMPT = """You are a trading journal voice assistant. You have a natural, warm,
conversational tone — like a knowledgeable trading buddy, not a form.

GOAL: Through natural conversation, collect the following data points
about the trade the user just took or is planning:
- Instrument (e.g. US30, EURUSD, XAUUSD)
- Direction (buy/long or sell/short)
- Entry price
- Stop loss
- Take profit / exit price (if trade is closed)
- Session (Asian/London/New York) — infer from time if not stated
- Setup/strategy used (e.g. support/resistance, breakout, order block)
- Reasoning/thesis for entering (freeform, capture in their words)
- Outcome (win/loss/breakeven, and P&L if mentioned)
- Emotional state or trade management notes (if volunteered)
- Screenshot of chart (prompt for this once, when it fits naturally)

RULES FOR CONVERSATION:
1. Never say things like "field," "enter," "next step," or "form."
   Speak like a person: "Nice, what was your entry?" not "Please
   state your entry price."
2. Ask ONE question at a time. Keep questions short.
3. If the user volunteers multiple data points in one answer, do NOT
   ask about those again. E.g. if they say "I went long on US30 at
   42500," you now have instrument, direction, and entry price —
   move on to whatever's still missing.
4. If the user gives reasoning or context ("I entered because price
   broke the 4H support"), capture that verbatim (or lightly cleaned
   up) as their trade thesis/notes — do not discard it, and do not
   force it into a single-word field.
5. When you have enough information to consider the entry complete,
   say so naturally ("Got it, that's everything I need") and prompt
   once for a chart screenshot if one hasn't been provided.
6. Keep your own responses SHORT — one sentence, sometimes two.
   You are not narrating what you're doing internally.
7. Never repeat back a robotic summary mid-conversation. Save the
   full structured summary for the very end.
8. If audio is unclear or a value seems ambiguous (e.g. a number
   that could be misheard), ask a quick clarifying question rather
   than guessing and logging wrong data. Trading data must be
   accurate — a misheard entry price is worse than an extra question.
9. End with a brief, human confirmation of what was logged, in
   plain spoken language, not a bulleted readout.

VOCABULARY:
- Directions: long, buy, went long, short, sell, sold, went short → trade_type BUY or SELL
- Sessions: Asian session, London session, New York session, London/NY overlap
- Setups: support/resistance, supply/demand, order block, breakout, retest, liquidity grab, trendline break, NFP/news
- Management: stop loss, take profit, trailing stop, breakeven, partial close, scaled out, floating P&L, drawdown
- Outcome: "it hit TP," "I got stopped out," "I closed early," "I'm still in it," "breakeven"

Prioritize correctly parsing a number that follows an instrument or price-related
word (entry, stop, target, exit, at, around). These are the highest-value,
highest-risk-of-error tokens. Never invent a price.

OUTPUT: Return JSON only:
{
  "reply": "short spoken response",
  "draft": {
    "symbol": "EURUSD" | null,
    "trade_type": "BUY" | "SELL" | null,
    "entry_price": number | null,
    "stop_loss": number | null,
    "take_profit": number | null,
    "exit_price": number | null,
    "status": "open" | "closed" | null,
    "session_type": string | null,
    "setup_tags": [string],
    "strategy": string | null,
    "thesis_notes": string | null,
    "emotions": [string],
    "lot_size": number | null,
    "outcome": "open" | "win" | "loss" | "breakeven" | null,
    "pnl": number | null
  },
  "complete": false,
  "ask_screenshot": false,
  "uncertain": []
}

Only set complete=true when symbol, trade_type, and entry_price are present
and you have either status or a clear sense they are still in the trade.
Set ask_screenshot=true once, when the entry is otherwise complete and no
chart has been provided. Do not ask emotions unless they bring it up.
Do not ask session if you can infer it from the clock hint.
"""

_QUESTIONS = (
    ("symbol", "What did you trade?"),
    ("trade_type", "Long or short?"),
    ("entry_price", "What was your entry?"),
    ("stop_loss", "Where did you put the stop?"),
    ("status", "Still in it, or already done?"),
    ("take_profit", "Any target?"),
    ("exit_price", "Where did you get out?"),
    ("thesis_notes", "What was the idea going in?"),
)

_EMPTY = {
    "symbol": None,
    "trade_type": None,
    "entry_price": None,
    "stop_loss": None,
    "take_profit": None,
    "exit_price": None,
    "status": None,
    "session_type": None,
    "setup_tags": [],
    "strategy": None,
    "thesis_notes": None,
    "emotions": [],
    "lot_size": None,
    "outcome": None,
    "pnl": None,
    "screenshot_prompted": False,
}


def empty_draft() -> Dict[str, Any]:
    """Blank conversational draft matching Trade fields."""
    return dict(_EMPTY, setup_tags=[], emotions=[])


def active_instrument_symbols(limit: int = 140) -> List[str]:
    """Symbols the model may mention — live from the catalog, not a hardcoded list."""
    try:
        rows = (
            Instrument.query.filter_by(is_active=True)
            .order_by(Instrument.symbol)
            .limit(max(20, min(int(limit), 200)))
            .all()
        )
    except Exception:
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30", "NAS100", "BTCUSD"]
    out = [str(r.symbol).upper() for r in rows if getattr(r, "symbol", None)]
    return out or ["EURUSD", "XAUUSD", "US30"]


def merge_draft(base: Optional[Dict[str, Any]], incoming: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep filled values; only overwrite with new non-empty data."""
    out = empty_draft()
    for src in (base or {}, incoming or {}):
        for key, val in src.items():
            if key not in out and key not in ("instrument_id", "screenshot_prompted"):
                continue
            if val in (None, "", []):
                continue
            if key in ("setup_tags", "emotions") and isinstance(val, list):
                seen = list(out.get(key) or [])
                for item in val:
                    s = str(item).strip()
                    if s and s not in seen:
                        seen.append(s)
                out[key] = seen[:8]
            elif key in ("entry_price", "stop_loss", "take_profit", "exit_price", "lot_size", "pnl"):
                try:
                    out[key] = float(val)
                except (TypeError, ValueError):
                    continue
            elif key == "trade_type":
                side = str(val).strip().upper()
                if side in ("SELL", "SHORT"):
                    out[key] = "SELL"
                elif side in ("BUY", "LONG"):
                    out[key] = "BUY"
            elif key == "status":
                st = str(val).strip().lower()
                if st in ("open", "closed"):
                    out[key] = st
            elif key == "symbol":
                out[key] = str(val).upper().replace("/", "")
            else:
                out[key] = val
        if src.get("screenshot_prompted"):
            out["screenshot_prompted"] = True
        if src.get("instrument_id"):
            out["instrument_id"] = src["instrument_id"]
    if out.get("setup_tags") and not out.get("strategy"):
        out["strategy"] = strategy_from_setups(out["setup_tags"])
    return out


def apply_parse(draft: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Fold regex/LLM parse_voice_text output into the conversation draft."""
    incoming: Dict[str, Any] = {}
    for key in (
        "symbol",
        "trade_type",
        "entry_price",
        "stop_loss",
        "take_profit",
        "exit_price",
        "lot_size",
        "session_type",
        "status",
    ):
        if parsed.get(key) not in (None, "", []):
            incoming[key] = parsed[key]
    if parsed.get("setup_tags"):
        incoming["setup_tags"] = parsed["setup_tags"]
    if parsed.get("emotions"):
        incoming["emotions"] = parsed["emotions"]
    if parsed.get("bare_number") is not None:
        if incoming.get("entry_price") is None and draft.get("entry_price") is None:
            incoming["entry_price"] = parsed["bare_number"]
        elif incoming.get("stop_loss") is None and draft.get("stop_loss") is None and draft.get("entry_price"):
            incoming["stop_loss"] = parsed["bare_number"]
        elif incoming.get("take_profit") is None and draft.get("take_profit") is None and draft.get("stop_loss"):
            incoming["take_profit"] = parsed["bare_number"]
        elif incoming.get("exit_price") is None and (draft.get("status") == "closed" or parsed.get("status") == "closed"):
            incoming["exit_price"] = parsed["bare_number"]
    return merge_draft(draft, incoming)


def missing_keys(draft: Dict[str, Any]) -> List[str]:
    """What the buddy should still ask — never a visible checklist."""
    missing: List[str] = []
    if not draft.get("symbol"):
        missing.append("symbol")
    if not draft.get("trade_type"):
        missing.append("trade_type")
    if draft.get("entry_price") is None:
        missing.append("entry_price")
    if draft.get("stop_loss") is None:
        missing.append("stop_loss")
    status = draft.get("status")
    if not status:
        missing.append("status")
    if status == "closed" and draft.get("exit_price") is None:
        if draft.get("take_profit") is None:
            missing.append("take_profit")
        missing.append("exit_price")
    elif status == "open" and draft.get("take_profit") is None:
        missing.append("take_profit")
    if not (draft.get("thesis_notes") or "").strip():
        missing.append("thesis_notes")
    return missing


def required_ready(draft: Dict[str, Any]) -> bool:
    """Enough to save a Trade row (same required columns as Add Trade)."""
    return bool(draft.get("symbol") and draft.get("trade_type") and draft.get("entry_price") is not None)


def fallback_opening(quick: bool = False) -> str:
    if quick:
        return "Give me the short version — pair, side, levels."
    return "Hey — tell me about the trade."


def _infer_closed_exit(draft: Dict[str, Any], transcript: str) -> Dict[str, Any]:
    t = (transcript or "").lower()
    if draft.get("status") != "closed" or draft.get("exit_price") is not None:
        return draft
    if re.search(r"\b(hit tp|took profit|target)\b", t) and draft.get("take_profit") is not None:
        draft = merge_draft(draft, {"exit_price": draft["take_profit"], "outcome": "win"})
    elif re.search(r"\b(stopped out|hit sl|stop(?:ped)?)\b", t) and draft.get("stop_loss") is not None:
        draft = merge_draft(draft, {"exit_price": draft["stop_loss"], "outcome": "loss"})
    elif re.search(r"\bbreakeven\b", t) and draft.get("entry_price") is not None:
        draft = merge_draft(draft, {"exit_price": draft["entry_price"], "outcome": "breakeven"})
    return draft


def fallback_turn(
    transcript: str,
    draft: Optional[Dict[str, Any]] = None,
    *,
    has_screenshot: bool = False,
    session_hint: Optional[Dict[str, Any]] = None,
    skip_screenshot: bool = False,
) -> Dict[str, Any]:
    """Deterministic conversation when the LLM is unavailable."""
    draft = merge_draft(empty_draft(), draft)
    text = (transcript or "").strip()
    yn = parse_yes_no(text) if text else None
    if text:
        parsed = parse_voice_text(text)
        draft = apply_parse(draft, parsed)
        if len(text) >= 12 and not draft.get("thesis_notes"):
            if any(w in text.lower() for w in ("because", "setup", "broke", "liquidity", "retest", "idea", "plan")):
                draft["thesis_notes"] = text[:2000]
        if yn == "no" and draft.get("screenshot_prompted"):
            skip_screenshot = True
        draft = _infer_closed_exit(draft, text)
        if not draft.get("session_type") and session_hint and session_hint.get("session_type"):
            draft["session_type"] = session_hint["session_type"]
        guessed, _ = normalize_symbol_guess(text)
        if guessed and not draft.get("symbol"):
            draft["symbol"] = guessed

    missing = missing_keys(draft)
    # Optional color — don't block the save.
    soft = {"take_profit", "thesis_notes"}
    hard = [k for k in missing if k not in soft]
    # Stop is high-value; keep it in hard unless they already skipped via "no stop"
    if "stop_loss" in missing and re.search(r"\b(no stop|without a stop|flat)\b", text.lower() if text else ""):
        hard = [k for k in hard if k != "stop_loss"]
        missing = [k for k in missing if k != "stop_loss"]

    ask_shot = False
    complete = False
    if hard:
        key = hard[0]
        reply = dict(_QUESTIONS)[key]
    elif not has_screenshot and not skip_screenshot and not draft.get("screenshot_prompted"):
        reply = "Got it — got a chart screenshot for this one?"
        ask_shot = True
        draft["screenshot_prompted"] = True
    else:
        reply = _spoken_wrap(draft)
        complete = required_ready(draft)

    return {
        "reply": reply,
        "draft": draft,
        "complete": complete,
        "ask_screenshot": ask_shot,
        "uncertain": [],
        "source": "fallback",
    }


def _spoken_wrap(draft: Dict[str, Any]) -> str:
    bits = []
    if draft.get("trade_type") and draft.get("symbol"):
        side = "long" if draft["trade_type"] == "BUY" else "short"
        bits.append(f"{side} {draft['symbol']}")
    if draft.get("entry_price") is not None:
        bits.append(f"from {draft['entry_price']:g}")
    state = "still open" if draft.get("status") != "closed" else "closed"
    core = " ".join(bits) if bits else "the trade"
    return f"Got it — {core}, {state}. I’ll put that in your journal."


def _llm_allowed() -> bool:
    if os.environ.get("OPENAI_VOICE_TURNS", "1").strip().lower() in ("0", "false", "no"):
        return False
    try:
        from flask import current_app

        if current_app and current_app.config.get("TESTING"):
            return False
    except Exception:
        pass
    return True


def _openai_turn(
    transcript: str,
    draft: Dict[str, Any],
    history: List[Dict[str, str]],
    instruments: List[str],
    session_hint: Optional[Dict[str, Any]],
    has_screenshot: bool,
) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or not _llm_allowed():
        return None
    clock = ""
    if session_hint:
        clock = f"Clock hint: {session_hint.get('chip') or ''} ({session_hint.get('session_type') or ''})."
    payload = {
        "model": os.environ.get("OPENAI_PARSE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "supported_instruments": instruments[:140],
                        "clock": clock,
                        "has_screenshot": has_screenshot,
                        "draft_so_far": draft,
                        "recent_turns": history[-12:],
                        "latest_user": transcript,
                    },
                    default=str,
                )[:12000],
            },
        ],
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=14,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        content = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or "{}"
        data = json.loads(content)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    reply = str(data.get("reply") or "").strip()
    if not reply:
        return None
    merged = merge_draft(draft, data.get("draft") if isinstance(data.get("draft"), dict) else {})
    uncertain = data.get("uncertain") if isinstance(data.get("uncertain"), list) else []
    ask_shot = bool(data.get("ask_screenshot"))
    complete = bool(data.get("complete")) and required_ready(merged)
    if ask_shot:
        merged["screenshot_prompted"] = True
    if complete and not has_screenshot and not merged.get("screenshot_prompted"):
        ask_shot = True
        complete = False
        merged["screenshot_prompted"] = True
        if "screenshot" not in reply.lower() and "chart" not in reply.lower():
            reply = "Got it — got a chart screenshot for this one?"
    return {
        "reply": reply[:280],
        "draft": merged,
        "complete": complete,
        "ask_screenshot": ask_shot,
        "uncertain": [str(x) for x in uncertain if x][:8],
        "source": "llm",
    }


def run_turn(
    transcript: str,
    draft: Optional[Dict[str, Any]] = None,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    has_screenshot: bool = False,
    session_hint: Optional[Dict[str, Any]] = None,
    skip_screenshot: bool = False,
    instruments: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """One user utterance → updated draft + the next spoken line."""
    draft = merge_draft(empty_draft(), draft)
    text = (transcript or "").strip()
    if not text:
        return {
            "reply": fallback_opening(),
            "draft": draft,
            "complete": False,
            "ask_screenshot": False,
            "uncertain": [],
            "source": "fallback",
        }

    parsed = parse_voice_text(text)
    seeded = apply_parse(draft, parsed)
    seeded = _infer_closed_exit(seeded, text)
    if not seeded.get("session_type") and session_hint and session_hint.get("session_type"):
        seeded["session_type"] = session_hint["session_type"]
    if parse_yes_no(text) == "no" and seeded.get("screenshot_prompted"):
        skip_screenshot = True

    llm = _openai_turn(
        text,
        seeded,
        history or [],
        instruments or active_instrument_symbols(),
        session_hint,
        has_screenshot,
    )
    if llm:
        if skip_screenshot:
            llm["ask_screenshot"] = False
            if required_ready(llm["draft"]):
                llm["complete"] = True
                llm["reply"] = _spoken_wrap(llm["draft"])
        return llm

    return fallback_turn(
        text,
        seeded,
        has_screenshot=has_screenshot,
        session_hint=session_hint,
        skip_screenshot=skip_screenshot,
    )


def draft_to_form_fields(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Map conversation draft onto the hidden Add Trade / guided fields."""
    tags = draft.get("setup_tags") or []
    emotions = draft.get("emotions") or []
    thesis = (draft.get("thesis_notes") or "").strip()
    status = draft.get("status") or ("closed" if draft.get("exit_price") is not None else "open")
    strategy = draft.get("strategy") or strategy_from_setups(tags)
    return {
        "symbol": draft.get("symbol") or "",
        "instrument_id": draft.get("instrument_id") or "",
        "trade_type": draft.get("trade_type") or "BUY",
        "entry_price": draft.get("entry_price") if draft.get("entry_price") is not None else "",
        "stop_loss": draft.get("stop_loss") if draft.get("stop_loss") is not None else "",
        "take_profit": draft.get("take_profit") if draft.get("take_profit") is not None else "",
        "exit_price": draft.get("exit_price") if draft.get("exit_price") is not None else "",
        "lot_size": draft.get("lot_size") or 1,
        "trade_log_status": status,
        "session_type": draft.get("session_type") or "",
        "strategy": strategy or "",
        "guide_session": draft.get("session_type") or "",
        "guide_why": thesis,
        "guide_voice_dump": thesis,
        "guide_emotions": ", ".join(emotions),
        "guide_feeling_before": emotions[0] if emotions else "",
        "guide_setup_tags": ", ".join(tags),
        "pre_trade_plan": thesis,
        "from_guide": "1",
        "from_voice": "1",
    }
