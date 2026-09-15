"""
Voice Journaling — parse speech, suggest sessions, and compose Trade fields.

Ask less. Extract more. Confirm prices. Save the same Trade row as manual Log Trade.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import load_only

from app import db
from app.models.trade import Trade
from app.utils.timeutil import resolve_zoneinfo, utc_now


# Spoken / informal names → canonical symbols (always confirm in the UI).
SYMBOL_ALIASES: Dict[str, str] = {
    "gold": "XAUUSD",
    "xau": "XAUUSD",
    "xauusd": "XAUUSD",
    "silver": "XAGUSD",
    "xag": "XAGUSD",
    "xagusd": "XAGUSD",
    "euro": "EURUSD",
    "euro dollar": "EURUSD",
    "eur usd": "EURUSD",
    "eurusd": "EURUSD",
    "cable": "GBPUSD",
    "pound": "GBPUSD",
    "gbp": "GBPUSD",
    "gbpusd": "GBPUSD",
    "yen": "USDJPY",
    "dollar yen": "USDJPY",
    "usdjpy": "USDJPY",
    "us30": "US30",
    "dow": "US30",
    "dow jones": "US30",
    "nas": "NAS100",
    "nasdaq": "NAS100",
    "nas100": "NAS100",
    "ustec": "NAS100",
    "spx": "SPX500",
    "spy": "SPX500",
    "sp500": "SPX500",
    "btc": "BTCUSD",
    "bitcoin": "BTCUSD",
    "btcusd": "BTCUSD",
    "eth": "ETHUSD",
    "ethereum": "ETHUSD",
}

EMOTION_CHIPS: Tuple[str, ...] = (
    "Calm",
    "Confident",
    "Nervous",
    "Fearful",
    "Greedy",
    "Frustrated",
    "Excited",
    "Impatient",
    "Revenge",
    "Uncertain",
    "Neutral",
)

# Chip / spoken label → Trade.emotion (must match config.EMOTIONS).
EMOTION_TO_CANONICAL: Dict[str, str] = {
    "calm focused": "Calm & Focused",
    "calm": "Calm & Focused",
    "confident": "Confident",
    "nervous": "Nervous",
    "fearful": "Fearful",
    "greedy": "Greedy",
    "frustrated": "Frustrated",
    "excited": "Excited",
    "impatient": "Impulsive",
    "revenge": "Revenge Trading",
    "uncertain": "Anxious",
    "neutral": "Calm & Focused",
    "fear": "Fearful",
    "fomo": "FOMO",
    "angry": "Angry",
    "tired": "Tired",
}

SETUP_CHIPS: Tuple[str, ...] = (
    "Breakout",
    "Retest",
    "Liquidity sweep",
    "Support/resistance",
    "Market structure",
    "Supply/demand",
    "Trend continuation",
    "Reversal",
    "Other",
)

SETUP_TO_STRATEGY: Dict[str, str] = {
    "breakout": "Breakout Trading",
    "retest": "Price Action",
    "liquidity sweep": "Smart Money Concepts (SMC)",
    "liquidity": "Smart Money Concepts (SMC)",
    "support/resistance": "Support & Resistance",
    "support resistance": "Support & Resistance",
    "market structure": "ICT Concepts",
    "supply/demand": "Supply & Demand",
    "supply demand": "Supply & Demand",
    "trend continuation": "Trend Following",
    "reversal": "Mean Reversion",
    "other": "Other",
}

SESSION_CHIPS: Tuple[Tuple[str, str], ...] = (
    ("Asia", "Asian Session"),
    ("London", "London Session"),
    ("New York", "New York Session"),
    ("London/New York overlap", "Overlap Sessions"),
    ("Other", "Overlap Sessions"),
)

_PRICE_RE = re.compile(
    r"(?<![\w.])(\d{1,6}(?:[.,]\d{1,6})?)(?![\w.])"
)
_LOT_RE = re.compile(
    r"\b(?:lot(?:s)?|size|position)\s*(?:of|is|was|at|:)?\s*(\d+(?:[.,]\d+)?)\b",
    re.I,
)
_LABELED_PRICE = (
    ("entry", re.compile(r"\b(?:entry|entered|fill)\s*(?:price)?\s*(?:at|was|is|:)?\s*(\d{1,6}(?:[.,]\d{1,6})?)\b", re.I)),
    ("stop_loss", re.compile(r"\b(?:stop(?:\s*loss)?|sl)\s*(?:at|was|is|:)?\s*(\d{1,6}(?:[.,]\d{1,6})?)\b", re.I)),
    ("take_profit", re.compile(r"\b(?:take\s*profit|target|tp)\s*(?:at|was|is|:)?\s*(\d{1,6}(?:[.,]\d{1,6})?)\b", re.I)),
    ("exit", re.compile(r"\b(?:exit(?:ed)?|closed?)\s*(?:at|price)?\s*(?:at|was|is|:)?\s*(\d{1,6}(?:[.,]\d{1,6})?)\b", re.I)),
)


def _to_float(raw: str) -> Optional[float]:
    s = (raw or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        parts = s.split(",")
        if len(parts[-1]) in (1, 2, 3, 4, 5):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


_SYMBOL_TOKEN_RE = re.compile(
    r"\b(XAUUSD|XAGUSD|EURUSD|GBPUSD|USDJPY|AUDUSD|USDCAD|NZDUSD|USDCHF|"
    r"BTCUSD|ETHUSD|US30|NAS100|SPX500|GER40|UK100|[A-Z]{3}USD|[A-Z]{3}JPY)\b"
)


def normalize_symbol_guess(text: str) -> Tuple[Optional[str], bool]:
    """
    Return (symbol, needs_confirm).

    needs_confirm is True when the match is an alias or a fuzzy spoken name.
    """
    raw = text or ""
    lower = re.sub(r"[^a-z0-9\s/]", " ", raw.lower())
    lower = re.sub(r"\s+", " ", lower).strip()
    if not lower:
        return None, False
    for alias in sorted(SYMBOL_ALIASES.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", lower):
            sym = SYMBOL_ALIASES[alias]
            compact = alias.replace(" ", "")
            needs = compact not in (
                "eurusd", "gbpusd", "usdjpy", "xauusd", "xagusd", "btcusd", "ethusd", "us30", "nas100"
            )
            return sym, needs
    m = _SYMBOL_TOKEN_RE.search(raw.upper().replace("/", ""))
    if m:
        token = m.group(1)
        if token.lower() in SYMBOL_ALIASES:
            return SYMBOL_ALIASES[token.lower()], False
        return token, False
    return None, False


def parse_side(text: str) -> Optional[str]:
    t = (text or "").lower()
    if re.search(r"\b(sell|sold|short|bearish)\b", t):
        return "SELL"
    if re.search(r"\b(buy|bought|long|bullish)\b", t):
        return "BUY"
    return None


def parse_yes_no(text: str) -> Optional[str]:
    t = (text or "").lower()
    if re.search(r"\b(yes|yeah|yep|yup|correct|right|confirm|okay|ok|sure)\b", t):
        if re.search(r"\b(nope|wrong|not correct)\b", t):
            return "no"
        return "yes"
    if re.search(r"\b(no|nope|nah|wrong|incorrect|change)\b", t):
        return "no"
    return None


def parse_status(text: str) -> Optional[str]:
    t = (text or "").lower()
    if re.search(r"\b(closed|done|finished|already (?:out|done|closed)|stopped out|hit (?:tp|sl))\b", t):
        return "closed"
    if re.search(r"\b(open|still in|running|holding|not closed)\b", t):
        return "open"
    return None


def parse_session(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "overlap" in t or ("london" in t and ("new york" in t or "ny" in t)):
        return "Overlap Sessions"
    if "london" in t:
        return "London Session"
    if "new york" in t or re.search(r"\bny\b", t) or "ny session" in t:
        return "New York Session"
    if "asia" in t or "tokyo" in t or "sydney" in t:
        return "Asian Session"
    return None


def parse_emotions(text: str) -> List[str]:
    t = (text or "").lower()
    found: List[str] = []
    for chip in EMOTION_CHIPS:
        key = chip.lower()
        if key in t or (key == "revenge" and "revenge" in t):
            found.append(chip)
    for spoken, canon_chip in (
        ("fomo", "Uncertain"),
        ("scared", "Fearful"),
        ("anxious", "Uncertain"),
        ("impatient", "Impatient"),
    ):
        if spoken in t and canon_chip not in found:
            found.append(canon_chip)
    return found


def parse_setup_tags(text: str) -> List[str]:
    t = (text or "").lower()
    tags: List[str] = []
    checks = (
        ("liquidity", "Liquidity sweep"),
        ("sweep", "Liquidity sweep"),
        ("bos", "Market structure"),
        ("choch", "Market structure"),
        ("change of character", "Market structure"),
        ("break of structure", "Market structure"),
        ("retest", "Retest"),
        ("breakout", "Breakout"),
        ("supply", "Supply/demand"),
        ("demand", "Supply/demand"),
        ("support", "Support/resistance"),
        ("resistance", "Support/resistance"),
        ("reversal", "Reversal"),
        ("continuation", "Trend continuation"),
        ("trend", "Trend continuation"),
    )
    for needle, tag in checks:
        if needle in t and tag not in tags:
            tags.append(tag)
    return tags


def canonical_emotion(chip_or_label: str) -> Optional[str]:
    key = re.sub(r"[^a-z]+", " ", (chip_or_label or "").lower()).strip()
    if not key:
        return None
    return EMOTION_TO_CANONICAL.get(key) or EMOTION_TO_CANONICAL.get(key.replace(" ", ""))


def strategy_from_setups(tags: List[str]) -> Optional[str]:
    for tag in tags or []:
        mapped = SETUP_TO_STRATEGY.get((tag or "").strip().lower())
        if mapped:
            return mapped
    return None


def suggest_session(when: Optional[datetime] = None, tz_name: str = "UTC") -> Dict[str, Any]:
    """London/NY/Asia from clock hour in the trader's timezone (best-effort)."""
    try:
        tz = resolve_zoneinfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)
    hour = local.hour
    # Approximate exchange hours in a typical trader TZ; always confirm.
    if 7 <= hour < 16:
        label, stored = "London", "London Session"
        if 12 <= hour < 16:
            label, stored = "London/New York overlap", "Overlap Sessions"
    elif 12 <= hour < 21:
        label, stored = "New York", "New York Session"
    else:
        label, stored = "Asia", "Asian Session"
    return {"chip": label, "session_type": stored, "hour": hour}


def parse_voice_text(text: str) -> Dict[str, Any]:
    """Extract trade fields from a spoken dump. Uncertain values are flagged, never silent."""
    raw = (text or "").strip()
    out: Dict[str, Any] = {
        "text": raw,
        "symbol": None,
        "symbol_needs_confirm": False,
        "trade_type": None,
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "exit_price": None,
        "lot_size": None,
        "session_type": None,
        "emotions": [],
        "setup_tags": [],
        "uncertain": [],
        "fields_found": [],
        "yes_no": None,
        "status": None,
        "bare_number": None,
    }
    if not raw:
        return out

    yn = parse_yes_no(raw)
    if yn:
        out["yes_no"] = yn
    st = parse_status(raw)
    if st:
        out["status"] = st
        out["fields_found"].append("status")

    symbol, confirm = normalize_symbol_guess(raw)
    if symbol:
        out["symbol"] = symbol
        out["symbol_needs_confirm"] = bool(confirm)
        out["fields_found"].append("symbol")
        if confirm:
            out["uncertain"].append("symbol")

    side = parse_side(raw)
    if side:
        out["trade_type"] = side
        out["fields_found"].append("trade_type")

    sess = parse_session(raw)
    if sess:
        out["session_type"] = sess
        out["fields_found"].append("session_type")

    emotions = parse_emotions(raw)
    if emotions:
        out["emotions"] = emotions
        out["fields_found"].append("emotions")

    setups = parse_setup_tags(raw)
    if setups:
        out["setup_tags"] = setups
        out["fields_found"].append("setup_tags")

    lot_m = _LOT_RE.search(raw)
    if lot_m:
        lot = _to_float(lot_m.group(1))
        if lot and 0 < lot < 500:
            out["lot_size"] = lot
            out["fields_found"].append("lot_size")

    labeled = {}
    for key, cre in _LABELED_PRICE:
        m = cre.search(raw)
        if m:
            val = _to_float(m.group(1))
            if val is not None:
                labeled[key] = val
                out[key if key != "entry" else "entry_price"] = val
                out["fields_found"].append("entry_price" if key == "entry" else key)

    if out.get("entry_price") is None:
        at_m = re.search(r"\b(?:at|around|from)\s+(\d{1,6}(?:[.,]\d{1,6})?)\b", raw, re.I)
        if at_m:
            at_val = _to_float(at_m.group(1))
            if at_val is not None and at_val not in (out.get("stop_loss"), out.get("take_profit"), out.get("exit_price")):
                out["entry_price"] = at_val
                out["fields_found"].append("entry_price")

    if out.get("entry_price") is None:
        nums = [_to_float(x) for x in _PRICE_RE.findall(raw)]
        nums = [n for n in nums if n is not None]
        if len(nums) == 1:
            out["bare_number"] = nums[0]
        elif len(nums) >= 3:
            out["entry_price"] = nums[0]
            out["stop_loss"] = nums[1]
            out["take_profit"] = nums[2]
            out["fields_found"].extend(["entry_price", "stop_loss", "take_profit"])
            out["uncertain"].extend(["entry_price", "stop_loss", "take_profit"])

    return out


def _focus_missing(parsed: Dict[str, Any], focus: str) -> bool:
    focus = (focus or "").strip()
    if focus in ("symbol",):
        return not parsed.get("symbol")
    if focus in ("direction", "trade_type"):
        return not parsed.get("trade_type")
    if focus in ("entry", "entry_price", "prices"):
        return parsed.get("entry_price") is None and parsed.get("bare_number") is None
    if focus in ("stop_loss", "sl"):
        return parsed.get("stop_loss") is None and parsed.get("bare_number") is None
    if focus in ("take_profit", "tp"):
        return parsed.get("take_profit") is None and parsed.get("bare_number") is None
    if focus in ("exit", "exit_price"):
        return parsed.get("exit_price") is None and parsed.get("bare_number") is None
    if focus in ("status",):
        return not parsed.get("status")
    return False


def enrich_parse_with_llm(parsed: Dict[str, Any], text: str, focus: str = "") -> Dict[str, Any]:
    """Fill gaps in messy speech (spoken numbers, nicknames) when OpenAI is configured."""
    import json
    import os

    import requests

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or not (text or "").strip():
        return parsed
    if not _focus_missing(parsed, focus) and parsed.get("symbol") and parsed.get("trade_type"):
        return parsed

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("OPENAI_PARSE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract trading journal fields from dictation. JSON keys: "
                            "symbol, trade_type (BUY|SELL), entry_price, stop_loss, take_profit, "
                            "exit_price, lot_size, session_type, status (open|closed), yes_no (yes|no), "
                            "emotions (array), setup_tags (array), bare_number. Use null when unknown. "
                            "Never invent prices. Map gold→XAUUSD, euro→EURUSD, nas/nasdaq→NAS100."
                        ),
                    },
                    {"role": "user", "content": text[:2000]},
                ],
            },
            timeout=12,
        )
    except requests.RequestException:
        return parsed
    if resp.status_code != 200:
        return parsed
    try:
        content = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or "{}"
        data = json.loads(content)
    except (ValueError, TypeError, json.JSONDecodeError):
        return parsed
    if not isinstance(data, dict):
        return parsed

    def _num(v):
        return _to_float(str(v)) if v is not None and v != "" else None

    for key, conv in (
        ("symbol", str),
        ("trade_type", str),
        ("session_type", str),
        ("status", str),
        ("yes_no", str),
        ("entry_price", _num),
        ("stop_loss", _num),
        ("take_profit", _num),
        ("exit_price", _num),
        ("lot_size", _num),
    ):
        if parsed.get(key) not in (None, "", []):
            continue
        if data.get(key) in (None, ""):
            continue
        val = conv(data.get(key))
        if key == "trade_type" and str(val).upper() in ("BUY", "SELL", "LONG", "SHORT"):
            parsed[key] = "SELL" if str(val).upper() in ("SELL", "SHORT") else "BUY"
            parsed.setdefault("fields_found", []).append(key)
        elif key == "symbol" and val:
            parsed[key] = str(val).upper().replace("/", "")
            parsed["symbol_needs_confirm"] = True
            parsed.setdefault("fields_found", []).append("symbol")
        elif key in ("entry_price", "stop_loss", "take_profit", "exit_price", "lot_size") and val is not None:
            parsed[key] = val
            parsed.setdefault("uncertain", []).append(key)
            parsed.setdefault("fields_found", []).append(key)
        elif key in ("session_type", "status", "yes_no") and val:
            parsed[key] = str(val).lower() if key != "session_type" else str(val)
            parsed.setdefault("fields_found", []).append(key)
    if not parsed.get("emotions") and isinstance(data.get("emotions"), list):
        parsed["emotions"] = [str(x) for x in data["emotions"] if x][:6]
    if not parsed.get("setup_tags") and isinstance(data.get("setup_tags"), list):
        parsed["setup_tags"] = [str(x) for x in data["setup_tags"] if x][:6]
    if parsed.get("entry_price") is None and _num(data.get("bare_number")) is not None:
        parsed["bare_number"] = _num(data.get("bare_number"))
    return parsed


def preview_metrics(
    *,
    entry: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    exit_price: Optional[float],
    side: str,
    lot_size: Optional[float],
    symbol: str = "",
) -> Dict[str, Any]:
    """Client-facing calculated fields — never asked, only shown."""
    direction = (side or "BUY").upper()
    metrics: Dict[str, Any] = {}
    if entry and stop_loss:
        sl_dist = abs(float(entry) - float(stop_loss))
        metrics["entry_to_sl"] = round(sl_dist, 6)
        if lot_size:
            metrics["risk_amount"] = round(sl_dist * float(lot_size), 2)
    if entry and take_profit:
        tp_dist = abs(float(take_profit) - float(entry))
        metrics["entry_to_tp"] = round(tp_dist, 6)
        if lot_size:
            metrics["reward_amount"] = round(tp_dist * float(lot_size), 2)
    if entry and stop_loss and take_profit:
        if direction == "SELL":
            risk = float(stop_loss) - float(entry)
            reward = float(entry) - float(take_profit)
        else:
            risk = float(entry) - float(stop_loss)
            reward = float(take_profit) - float(entry)
        if risk > 0 and reward > 0:
            metrics["rr"] = round(reward / risk, 2)
            metrics["rr_label"] = f"1:{round(reward / risk, 2):g}"
    if entry and exit_price:
        if direction == "SELL":
            pnl_dist = float(entry) - float(exit_price)
        else:
            pnl_dist = float(exit_price) - float(entry)
        metrics["pl_distance"] = round(pnl_dist, 6)
        if lot_size:
            metrics["profit_loss"] = round(pnl_dist * float(lot_size), 2)
    pip = 0.0001
    sym = (symbol or "").upper()
    if "JPY" in sym:
        pip = 0.01
    elif any(x in sym for x in ("XAU", "GOLD", "XAG")):
        pip = 0.1
    elif any(x in sym for x in ("US30", "NAS", "SPX", "GER", "UK100")):
        pip = 1.0
    elif any(x in sym for x in ("BTC", "ETH")):
        pip = 1.0
    if metrics.get("entry_to_sl"):
        metrics["sl_pips"] = round(metrics["entry_to_sl"] / pip, 1)
    if metrics.get("entry_to_tp"):
        metrics["tp_pips"] = round(metrics["entry_to_tp"] / pip, 1)
    return metrics


def compose_guided_fields(form) -> Optional[Dict[str, Any]]:
    """Turn Voice Journal / guided answers into Trade note fields."""
    if (form.get("from_guide") or "").strip() != "1":
        return None

    before = (form.get("guide_feeling_before") or "").strip()
    why = (form.get("guide_why") or "").strip()
    followed = (form.get("guide_followed_plan") or "").strip().lower()
    confirms = [c.strip() for c in form.getlist("guide_confirm") if (c or "").strip()]
    after = (form.get("guide_feeling_after") or "").strip()
    happened = (form.get("guide_what_happened") or "").strip()
    reflection = (form.get("guide_reflection") or "").strip()
    voice_dump = (form.get("guide_voice_dump") or "").strip()
    emotions_raw = (form.get("guide_emotions") or "").strip()
    setups_raw = (form.get("guide_setup_tags") or "").strip()
    session = (form.get("session_type") or form.get("guide_session") or "").strip()
    moved_sl = (form.get("guide_moved_sl") or "").strip().lower()
    early = (form.get("guide_early_close") or "").strip().lower()
    partials = (form.get("guide_partials") or "").strip().lower()
    added = (form.get("guide_added") or "").strip().lower()
    mgmt_note = (form.get("guide_mgmt_note") or "").strip()

    emotion_chips = [p.strip() for p in emotions_raw.split(",") if p.strip()]
    setup_tags = [p.strip() for p in setups_raw.split(",") if p.strip()]

    pre_bits: List[str] = []
    if before:
        pre_bits.append(f"Feeling before: {before}")
    if emotion_chips:
        pre_bits.append("Emotions: " + ", ".join(emotion_chips))
    if why:
        pre_bits.append(why)
    elif voice_dump:
        pre_bits.append(voice_dump[:2000])
    if setup_tags:
        pre_bits.append("Setup: " + ", ".join(setup_tags))
    if session:
        pre_bits.append(f"Session: {session}")
    if followed:
        pre_bits.append(f"Followed the plan: {followed}")
    if confirms:
        pre_bits.append("Checked: " + ", ".join(confirms))

    post_bits: List[str] = []
    if after:
        post_bits.append(f"Feeling after: {after}")
    if happened:
        post_bits.append(happened)
    mgmt_bits = []
    if moved_sl in ("yes", "true", "1"):
        mgmt_bits.append("Moved stop")
    if early in ("yes", "true", "1"):
        mgmt_bits.append("Closed early")
    if partials in ("yes", "true", "1"):
        mgmt_bits.append("Took partials")
    if added in ("yes", "true", "1"):
        mgmt_bits.append("Added to position")
    if mgmt_bits:
        post_bits.append("Management: " + ", ".join(mgmt_bits))
    if mgmt_note:
        post_bits.append(mgmt_note)
    if reflection:
        post_bits.append("Next time: " + reflection)

    pre = "\n".join(pre_bits).strip()
    post = "\n".join(post_bits).strip()
    if not pre and voice_dump:
        pre = voice_dump[:2000]
    if not post and voice_dump and len(voice_dump) > 20:
        post = voice_dump[:2000]

    canon = None
    for chip in emotion_chips:
        canon = canonical_emotion(chip)
        if canon:
            break
    if not canon:
        canon = canonical_emotion(after) or canonical_emotion(before) or canonical_emotion(form.get("emotion") or "")
    emotion = canon or after or before or (form.get("emotion") or "").strip() or None

    checklist = form.get("checklist_completed") == "on" or "confirmed" in confirms or "premarket" in confirms
    playbook = (
        form.get("playbook_followed") == "on"
        or followed in ("yes", "true", "on", "mostly")
        or "playbook" in confirms
    )
    strategy = strategy_from_setups(setup_tags)
    tags = ", ".join(setup_tags)[:255] if setup_tags else None
    lessons = reflection or None

    return {
        "pre_trade_plan": pre,
        "post_trade_notes": post,
        "emotion": emotion or None,
        "checklist_completed": checklist,
        "playbook_followed": playbook,
        "strategy": strategy,
        "session_type": session or None,
        "tags": tags,
        "lessons_learned": lessons,
    }


def _is_journaled(trade: Trade) -> bool:
    notes = (trade.post_trade_notes or "").strip()
    lessons = (trade.lessons_learned or "").strip()
    plan = (trade.pre_trade_plan or "").strip()
    before = (getattr(trade, "before_screenshot", None) or "").strip()
    after = (getattr(trade, "after_screenshot", None) or "").strip()
    return bool(notes or lessons or plan or before or after)


def today_journal_status(user_id: int, tz_name: str = "UTC") -> Dict[str, Any]:
    """Dashboard Journal Status: today's logs vs missing reflection."""
    try:
        tz = resolve_zoneinfo(tz_name)
    except Exception:
        tz = timezone.utc
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = start_utc + timedelta(days=1)

    today_rows: List[Trade] = []
    pending: List[Trade] = []
    try:
        today_rows = (
            Trade.query.options(
                load_only(
                    Trade.id,
                    Trade.symbol,
                    Trade.trade_type,
                    Trade.status,
                    Trade.entry_date,
                    Trade.created_at,
                    Trade.pre_trade_plan,
                    Trade.post_trade_notes,
                    Trade.lessons_learned,
                    Trade.before_screenshot,
                    Trade.after_screenshot,
                )
            )
            .filter(
                Trade.user_id == user_id,
                Trade.entry_date >= start_utc,
                Trade.entry_date < end_utc,
            )
            .order_by(Trade.entry_date.desc())
            .all()
        )
        lookback = utc_now() - timedelta(days=7)
        recent = (
            Trade.query.options(
                load_only(
                    Trade.id,
                    Trade.symbol,
                    Trade.trade_type,
                    Trade.status,
                    Trade.entry_date,
                    Trade.exit_date,
                    Trade.pre_trade_plan,
                    Trade.post_trade_notes,
                    Trade.lessons_learned,
                    Trade.before_screenshot,
                    Trade.after_screenshot,
                )
            )
            .filter(
                Trade.user_id == user_id,
                Trade.status == "CLOSED",
                Trade.entry_date >= lookback,
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(40)
            .all()
        )
        pending = [t for t in recent if not _is_journaled(t)]
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        today_rows = []
        pending = []

    journaled = [t for t in today_rows if _is_journaled(t)]
    missing_today = [t for t in today_rows if not _is_journaled(t)]

    def _brief(t: Trade) -> Dict[str, Any]:
        when = t.exit_date or t.entry_date
        return {
            "id": t.id,
            "symbol": t.symbol,
            "trade_type": t.trade_type,
            "status": t.status,
            "when": when.isoformat() if when else None,
        }

    return {
        "today_total": len(today_rows),
        "today_journaled": len(journaled),
        "today_missing": len(missing_today),
        "pending_count": len(pending),
        "pending": [_brief(t) for t in pending[:8]],
        "first_missing_id": (pending[0].id if pending else (missing_today[0].id if missing_today else None)),
    }
