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


SYSTEM_PROMPT = """You are a premium trading journal voice coach. Warm, concise, professional —
like a mentor reviewing the trade with them, never a form wizard.

GOAL: Collect a COMPLETE journal page through natural conversation:
TRADE FACTS
- Instrument (e.g. US30, EURUSD, XAUUSD, gold)
- Direction (buy/long or sell/short)
- Entry, stop, take profit / exit (if closed)
- Session + rough entry time
- Setup/strategy tags if mentioned
REFLECTION (always ask these if missing — this is the journal)
- Why they entered (thesis — their words verbatim)
- Whether they followed their rules / playbook
- How they felt DURING the trade
- How they felt AFTER (or now, if still open)
- What they learned
- How they will improve next time
Then BEFORE chart, then AFTER chart (skip only if they decline).

RULES:
1. Never say "field," "step," "form," or "next question."
2. Ask ONE short question at a time. Acknowledge briefly, then ask.
3. Never re-ask a key already in already_captured / draft_so_far.
4. thesis_notes, lessons, improve_next, feeling_during, feeling_after MUST be
   the user's own words (light um/uh clean only). Never paraphrase.
5. followed_plan is yes / no / mostly from their answer.
6. Prefer clarifying a misheard PRICE over guessing. Trading numbers must be exact.
7. Keep replies to one sentence, sometimes two. One question mark max.
8. Know trading vocabulary: liquidity sweep, BOS, CHoCH, order block, FVG,
   retest, breakout, partials, trailing stop, R:R, pip, lot, session open.

OUTPUT JSON only:
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
    "followed_plan": "yes" | "no" | "mostly" | null,
    "feeling_during": string | null,
    "feeling_after": string | null,
    "lessons": string | null,
    "improve_next": string | null,
    "emotions": [string],
    "lot_size": number | null,
    "outcome": "open" | "win" | "loss" | "breakeven" | null,
    "pnl": number | null
  },
  "complete": false,
  "ask_screenshot": false,
  "screenshot_kind": "" | "before" | "after",
  "uncertain": []
}

complete=true only when trade facts + reflection keys are filled (or clearly
skipped by the user) and screenshots are done or declined.
"""

_QUESTIONS = (
    ("symbol", "What did you trade?"),
    ("trade_type", "Were you long or short?"),
    ("entry_price", "What was your entry?"),
    ("stop_loss", "Where was the stop?"),
    ("status", "Still in it, or already done?"),
    ("session_type", "Which session — London, New York, or Asia?"),
    ("entry_time", "About what time did you enter?"),
    ("take_profit", "Any target on it?"),
    ("exit_price", "Where did you get out?"),
    ("lot_size", "What size were you trading?"),
    ("thesis_notes", "Why did you enter — what was the idea?"),
    ("followed_plan", "Did you follow your rules on this one?"),
    ("feeling_during", "How were you feeling during the trade?"),
    ("feeling_after", "And how do you feel about it now?"),
    ("lessons", "What did you learn from this trade?"),
    ("improve_next", "What will you do differently next time?"),
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
    "followed_plan": None,
    "feeling_during": None,
    "feeling_after": None,
    "lessons": None,
    "improve_next": None,
    "emotions": [],
    "lot_size": None,
    "outcome": None,
    "pnl": None,
    "voice_dump": None,
    "entry_time": None,
    "voice_mode": None,
    "screenshot_prompted": False,
    "screenshot_before": False,
    "screenshot_after": False,
    "stop_skipped": False,
    "tp_skipped": False,
    "reflection_skipped": False,
    "lot_skipped": False,
}

_SHORT_ANSWER = re.compile(
    r"^(yes|no|yeah|yep|yup|nope|nah|ok|okay|sure|correct|right|"
    r"that's right|thats right|long|short|buy|sell|open|closed|"
    r"still in it|already done|done|london|new york|asia|asian|"
    r"not sure|don't remember|dont remember|no idea|"
    r"no screenshot|i uploaded the chart|i uploaded the before|"
    r"i uploaded the after|[\d.,\s]+)$",
    re.I,
)

_FILLED_ASK = (
    ("symbol", ("what did you trade", "which pair", "what market", "what instrument")),
    ("trade_type", ("long or short", "buy or sell", "which side", "were you long")),
    ("entry_price", ("your entry", "entry price", "where did you get in", "what was the entry")),
    ("stop_loss", ("the stop", "stop loss", "where did you put the stop", "where was the stop")),
    ("entry_time", ("what time did you enter", "about what time", "what time was it")),
    ("take_profit", ("any target", "take profit", "your target")),
    ("exit_price", ("get out", "where did you close", "exit price")),
    ("status", ("still in it, or already", "already done?", "still in it or")),
    ("session_type", ("which session", "london, new york", "what session")),
    ("thesis_notes", ("the idea going in", "what was the idea", "why did you enter")),
    ("lot_size", ("what size", "how many lots", "lot size", "position size")),
    ("followed_plan", ("follow your rules", "followed your rules", "follow the plan", "followed the plan")),
    ("feeling_during", ("feeling during", "feel during", "how were you feeling during")),
    ("feeling_after", ("feel about it now", "feeling after", "how do you feel about it now")),
    ("lessons", ("what did you learn", "what have you learnt", "lesson")),
    ("improve_next", ("differently next time", "improve next", "next time")),
)

_REASON_HINTS = (
    "because", "setup", "broke", "liquidity", "retest", "idea", "plan",
    "swept", "bos", "order block", "support", "resistance", "breakout",
    "fvg", "fair value", "choch", "rules", "discipline",
)

_REFLECT_KEYS = (
    "thesis_notes",
    "followed_plan",
    "feeling_during",
    "feeling_after",
    "lessons",
    "improve_next",
)

_TIME_RE = re.compile(
    r"\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|this morning|this afternoon|"
    r"this evening|last night|overnight|london open|ny open|"
    r"new york open|asia open|around \d{1,2}|"
    r"(?:london|ny|new york|asia)?\s*morning|"
    r"(?:london|ny|new york|asia)?\s*afternoon)\b",
    re.I,
)


def _extract_entry_time(text: str) -> Optional[str]:
    m = _TIME_RE.search(text or "")
    return m.group(0).strip() if m else None


def _skipped_time(text: str) -> bool:
    t = (text or "").lower()
    return bool(re.search(r"\b(not sure|don't remember|dont remember|no idea|skip(?:ped)? it)\b", t))


_CORR_RE = re.compile(
    r"\b(actually|wait|correction|meant|make that|change(?:d)?(?: that| the| it)?|"
    r"wrong|not that|update(?:d)?)\b",
    re.I,
)


def _skipped_target(text: str) -> bool:
    t = (text or "").lower()
    return bool(re.search(
        r"\b(no target|no tp|without a target|didn't set (?:a )?target|"
        r"dont set (?:a )?target|no take profit|didn't have a target)\b",
        t,
    ))


def _declines_shot(text: str, prompted: bool) -> bool:
    if not prompted:
        return False
    t = (text or "").lower()
    if re.search(r"\b(no screenshot|not this time|don't have|dont have|skip(?:ped)? (?:it|the chart))\b", t):
        return True
    if _CORR_RE.search(t) or re.search(r"\d", t):
        return False
    return parse_yes_no(t) == "no"


def _draft_metrics(draft: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.voice_journal import preview_metrics

    return preview_metrics(
        entry=draft.get("entry_price"),
        stop_loss=draft.get("stop_loss"),
        take_profit=draft.get("take_profit"),
        exit_price=draft.get("exit_price"),
        side=draft.get("trade_type") or "BUY",
        lot_size=draft.get("lot_size") or 1.0,
        symbol=draft.get("symbol") or "",
    )


def empty_draft() -> Dict[str, Any]:
    """Blank conversational draft matching Trade fields."""
    return dict(_EMPTY, setup_tags=[], emotions=[])


def draft_from_existing(prefill: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Seed a conversation draft from an open trade the user is finishing."""
    if not isinstance(prefill, dict) or not prefill:
        return empty_draft()
    status = str(prefill.get("status") or "").upper()
    seeded = {
        "symbol": prefill.get("symbol"),
        "instrument_id": prefill.get("instrument_id"),
        "trade_type": prefill.get("trade_type"),
        "entry_price": prefill.get("entry_price"),
        "stop_loss": prefill.get("stop_loss"),
        "take_profit": prefill.get("take_profit"),
        "exit_price": prefill.get("exit_price"),
        "lot_size": prefill.get("lot_size"),
        "session_type": prefill.get("session_type"),
        "strategy": prefill.get("strategy"),
        "status": "closed" if status == "CLOSED" else ("open" if status == "OPEN" else None),
        "thesis_notes": (prefill.get("pre_trade_plan") or "").strip() or None,
        "voice_dump": (prefill.get("post_trade_notes") or prefill.get("pre_trade_plan") or "").strip() or None,
    }
    return merge_draft(empty_draft(), seeded)


_SAVE_CONFIRM_RE = re.compile(
    r"\b(save(?:\s+it)?|log(?:\s+it)?|looks good|that'?s (?:it|right|correct)|"
    r"confirm|submit|go ahead|yes(?: please)?|yep|yeah|perfect)\b",
    re.I,
)


def is_save_confirm(text: str) -> bool:
    """True when the trader is confirming the review card should be saved."""
    t = _light_clean(text or "")
    if not t:
        return False
    if _CORR_RE.search(t):
        return False
    if re.search(r"\b(change|fix|wrong|edit|update|wait)\b", t, re.I):
        return False
    return bool(_SAVE_CONFIRM_RE.search(t))


def _token_set(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _token_overlap(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(max(1, min(len(sa), len(sb))))


def _light_clean(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"\b(u+m+|u+h+|er+|ah+)\b", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _is_short_field_answer(text: str) -> bool:
    t = _light_clean(text)
    if not t:
        return True
    if _SHORT_ANSWER.match(t):
        return True
    words = t.split()
    if len(words) <= 3 and not any(h in t.lower() for h in _REASON_HINTS):
        return True
    return False


def _user_turns(history: Optional[List[Dict[str, str]]], latest: str) -> List[str]:
    bits: List[str] = []
    for row in history or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "") != "user":
            continue
        content = _light_clean(str(row.get("content") or ""))
        if content and (not bits or bits[-1] != content):
            bits.append(content)
    last = _light_clean(latest)
    if last and (not bits or bits[-1] != last):
        bits.append(last)
    return bits


def _substantial_line(text: str) -> bool:
    t = _light_clean(text)
    if not t or _is_short_field_answer(t):
        return False
    words = t.split()
    return len(words) >= 6 or any(h in t.lower() for h in _REASON_HINTS)


def _levels_only_dump(text: str) -> bool:
    """True when a line is mostly pair/side/levels — not a real thesis."""
    t = _light_clean(text)
    if not t:
        return True
    low = t.lower()
    if any(h in low for h in _REASON_HINTS):
        return False
    has_levels = bool(
        re.search(r"\b(long|short|buy|sell|bought|sold)\b", low)
        and re.search(r"\b(stop|target|tp|sl|at)\b", low)
        and re.search(r"\d", low)
    )
    return has_levels


def _thin_reflection(text: str, key: str) -> bool:
    """True when a lessons/improve/thesis reply is too thin to keep."""
    t = _light_clean(text)
    if not t:
        return True
    words = t.split()
    if key == "thesis_notes":
        return _is_short_field_answer(t) and not any(h in t.lower() for h in _REASON_HINTS)
    if key in ("lessons", "improve_next"):
        if len(words) <= 1:
            return True
        if len(words) == 2 and parse_yes_no(t) in ("yes", "no"):
            return True
        return False
    return False


def _best_spoken_thesis(candidates: List[str]) -> str:
    """Pick the strongest user-spoken idea line (never a polished rewrite)."""
    for turn in reversed(candidates):
        low = turn.lower()
        if _levels_only_dump(turn):
            continue
        if _substantial_line(turn) and any(
            h in low for h in ("because", "idea", "thesis", "setup", "sweep", "break", "retest", "liquidity")
        ):
            return turn[:2000]
    for turn in reversed(candidates):
        if _levels_only_dump(turn):
            continue
        if _substantial_line(turn):
            return turn[:2000]
    return ""


def _capture_user_words(
    draft: Dict[str, Any],
    transcript: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Keep thesis / voice_dump as what the user said — never a rewrite."""
    turns = _user_turns(history, transcript)
    dump = "\n".join(turns).strip()[:8000]
    prev_dump = str(draft.get("voice_dump") or "").strip()
    if dump and prev_dump:
        if dump in prev_dump:
            draft["voice_dump"] = prev_dump
        elif prev_dump in dump:
            draft["voice_dump"] = dump
        else:
            draft["voice_dump"] = (prev_dump + "\n" + dump).strip()[:8000]
    elif dump:
        draft["voice_dump"] = dump
    elif prev_dump:
        draft["voice_dump"] = prev_dump

    existing = _light_clean(str(draft.get("thesis_notes") or ""))
    if existing in ("skipped",):
        existing = ""
    latest = _light_clean(transcript)
    blob = str(draft.get("voice_dump") or dump or "")
    candidates = list(turns)
    for line in reversed(blob.split("\n")):
        line = line.strip()
        if line and line not in candidates:
            candidates.append(line)

    # If thesis was rewritten away from spoken words, restore the user's line.
    dump_l = blob.lower()
    if existing and dump_l and existing.lower() not in dump_l:
        restored = _best_spoken_thesis(candidates)
        if restored:
            draft["thesis_notes"] = restored
            return draft

    hard = _hard_missing(draft, transcript)
    # Freeze thesis once we already have one and we're on reflection prompts.
    if existing and hard and hard[0] in _REFLECT_KEYS:
        draft["thesis_notes"] = existing[:2000]
        return draft

    if existing:
        why_like = any(h in latest.lower() for h in ("because", "idea", "thesis", "setup", "plan was"))
        if latest and _substantial_line(latest) and why_like and latest.lower() not in existing.lower():
            draft["thesis_notes"] = (existing + " " + latest).strip()[:2000]
        else:
            draft["thesis_notes"] = existing[:2000]
        return draft

    spoken = _best_spoken_thesis(candidates)
    if spoken:
        draft["thesis_notes"] = spoken
    return draft


def _asks_about_filled(reply: str, draft: Dict[str, Any]) -> bool:
    r = (reply or "").lower()
    if not r:
        return False
    for key, hints in _FILLED_ASK:
        val = draft.get(key)
        if val in (None, "", []):
            continue
        if any(h in r for h in hints):
            return True
    return False


def _one_question(reply: str) -> str:
    text = (reply or "").strip()
    if text.count("?") <= 1:
        return text
    first, _rest = text.split("?", 1)
    return (first.strip() + "?") if first.strip() else text


def _hard_missing(draft: Dict[str, Any], transcript: str = "") -> List[str]:
    missing = missing_keys(draft)
    soft = {"take_profit"}
    if (draft.get("voice_mode") or "") == "quick":
        # Quick mode still gets thesis + rules; deeper feelings are soft.
        soft |= {"feeling_during", "feeling_after", "lessons", "improve_next", "entry_time", "lot_size"}
    hard = [k for k in missing if k not in soft]
    t = (transcript or "").lower()
    if "stop_loss" in hard and (draft.get("stop_skipped") or re.search(r"\b(no stop|without a stop|flat)\b", t)):
        hard = [k for k in hard if k != "stop_loss"]
    if "take_profit" in hard and (draft.get("tp_skipped") or _skipped_target(t)):
        hard = [k for k in hard if k != "take_profit"]
    if "entry_time" in hard and _skipped_time(t):
        hard = [k for k in hard if k != "entry_time"]
    if "lot_size" in hard and (
        draft.get("lot_skipped")
        or re.search(r"\b(default size|standard size|skip(?:ped)? (?:size|lots?)|not sure (?:of |about )?size)\b", t)
    ):
        draft["lot_skipped"] = True
        hard = [k for k in hard if k != "lot_size"]
    if draft.get("reflection_skipped"):
        hard = [k for k in hard if k not in _REFLECT_KEYS]
    return hard


def _parse_followed_plan(text: str) -> Optional[str]:
    t = (text or "").lower()
    # Avoid "no target" / "no stop" flipping the rules answer.
    if re.search(r"\bno\s+(target|tp|stop|screenshot|chart)\b", t):
        t = re.sub(r"\bno\s+(target|tp|stop|screenshot|chart)\b", " ", t)
    if re.search(r"\b(mostly|kinda|kind of|sort of|partially)\b", t):
        return "mostly"
    if re.search(r"\b(followed|stuck to|disciplined|by the book)\b", t) and not re.search(
        r"\b(didn't|did not|broke)\b", t
    ):
        return "yes"
    if re.search(r"\b(broke (?:my |the )?rules|didn't follow|did not follow|revenge|fomo'd|fomoed)\b", t):
        return "no"
    yn = parse_yes_no(t)
    if yn == "yes":
        return "yes"
    if yn == "no" and re.search(r"\b(rules?|plan|playbook|follow)\b", t):
        return "no"
    if yn == "no" and len(t.split()) <= 3:
        return "no"
    if yn == "yes" and len(t.split()) <= 3:
        return "yes"
    return None


def _skipped_reflection(text: str) -> bool:
    t = (text or "").lower().strip()
    return bool(re.search(
        r"\b(skip(?:ped)?(?: reflection| that| it)?|nothing to add|no lesson|"
        r"not sure|don't know|dont know|no idea|pass)\b",
        t,
    ))


def _fill_reflection_slot(draft: Dict[str, Any], key: str, text: str) -> Dict[str, Any]:
    """Store the user's exact words into the open reflection slot."""
    cleaned = _light_clean(text)
    if not cleaned:
        return draft
    if key == "followed_plan":
        plan = _parse_followed_plan(cleaned)
        if plan:
            draft["followed_plan"] = plan
            draft["_just_reflected"] = "followed_plan"
        return draft
    if key in ("feeling_during", "feeling_after"):
        if _CORR_RE.search(cleaned) and not re.search(
            r"\b(feel|calm|nervous|anxious|proud|fear|patient|disciplin)\b", cleaned, re.I
        ):
            return draft
        draft[key] = cleaned[:400]
        draft["_just_reflected"] = key
        if key == "feeling_during":
            draft.setdefault("emotions", [])
            if isinstance(draft["emotions"], list) and cleaned[:40] not in draft["emotions"]:
                draft["emotions"] = (draft["emotions"] + [cleaned[:40]])[:6]
        return draft
    if _thin_reflection(cleaned, key):
        return draft
    if key == "thesis_notes" and (
        not draft.get("thesis_notes") or _levels_only_dump(str(draft.get("thesis_notes") or ""))
    ):
        draft["thesis_notes"] = cleaned[:2000]
        draft["_just_reflected"] = key
    elif key == "lessons" and not draft.get("lessons"):
        draft["lessons"] = cleaned[:1200]
        draft["_just_reflected"] = key
    elif key == "improve_next" and not draft.get("improve_next"):
        draft["improve_next"] = cleaned[:1200]
        draft["_just_reflected"] = key
    return draft


def _apply_reflection_answer(draft: Dict[str, Any], text: str) -> Dict[str, Any]:
    """When the open question is reflection, capture the reply into that slot."""
    if _skipped_reflection(text):
        facts_left = [k for k in _hard_missing(draft, text) if k not in _REFLECT_KEYS]
        if not facts_left:
            draft["reflection_skipped"] = True
            for key in _REFLECT_KEYS:
                if not draft.get(key):
                    draft[key] = "skipped" if key != "followed_plan" else "mostly"
            return draft
    hard = _hard_missing(draft, text)
    if not hard or hard[0] not in _REFLECT_KEYS:
        why_hints = ("because", "idea", "thesis", "i entered", "went in because", "my plan")
        low = (text or "").lower()
        if (
            not draft.get("thesis_notes")
            and _substantial_line(text)
            and any(h in low for h in why_hints)
        ):
            draft["thesis_notes"] = _light_clean(text)[:2000]
        plan = _parse_followed_plan(text)
        if (
            plan
            and not draft.get("followed_plan")
            and re.search(r"\b(rules?|plan|playbook|disciplin|follow)\b", low)
        ):
            draft["followed_plan"] = plan
        return draft
    return _fill_reflection_slot(draft, hard[0], text)

def _ack_from_last(text: str, draft: Dict[str, Any]) -> str:
    """A short spoken nod so the next question feels like a conversation."""
    reflected = draft.pop("_just_reflected", None)
    if reflected:
        snippet = _light_clean(text)
        if reflected == "followed_plan":
            plan = draft.get("followed_plan")
            if plan == "yes":
                return "Good — you stayed with the rules."
            if plan == "no":
                return "Okay — noted you broke the rules."
            if plan == "mostly":
                return "Okay — mostly on plan."
        if reflected in ("feeling_during", "feeling_after") and snippet:
            bit = snippet.split(",")[0].strip()
            if len(bit) > 42:
                bit = bit[:40].rstrip() + "…"
            return f"Got it — {bit}."
        if reflected in ("lessons", "improve_next", "thesis_notes") and snippet:
            return "Got it."
        return "Got it."
    corr = draft.get("_just_corrected") or []
    if corr:
        labels: List[str] = []
        names = {
            "entry_price": "entry",
            "stop_loss": "stop",
            "take_profit": "target",
            "exit_price": "exit",
            "trade_type": "side",
            "symbol": "market",
            "session_type": "session",
            "lot_size": "size",
        }
        for key in corr[:3]:
            if key == "trade_type":
                labels.append("short" if draft.get("trade_type") == "SELL" else "long")
            elif key in ("entry_price", "stop_loss", "take_profit", "exit_price", "lot_size") and draft.get(key) is not None:
                labels.append(f"{names[key]} {float(draft[key]):g}")
            elif key == "symbol" and draft.get("symbol"):
                labels.append(str(draft["symbol"]))
            elif key in names:
                labels.append(names[key])
        if labels:
            return "Updated — " + ", ".join(labels) + "."
        return "Updated."
    parsed = parse_voice_text(text or "")
    bits: List[str] = []
    if parsed.get("symbol"):
        bits.append(str(parsed["symbol"]))
    if parsed.get("trade_type"):
        bits.append("long" if parsed["trade_type"] == "BUY" else "short")
    if parsed.get("entry_price") is not None:
        bits.append(f"entry {float(parsed['entry_price']):g}")
    elif parsed.get("stop_loss") is not None:
        bits.append(f"stop {float(parsed['stop_loss']):g}")
    if parsed.get("status") == "open":
        bits.append("still in")
    elif parsed.get("status") == "closed":
        bits.append("closed")
    if parsed.get("session_type"):
        bits.append(str(parsed["session_type"]).replace(" Session", ""))
    time_bit = _extract_entry_time(text or "")
    if time_bit and "entry_time" not in "".join(bits).lower():
        bits.append(time_bit)
    if parsed.get("take_profit") is not None and len(bits) < 3:
        bits.append(f"target {float(parsed['take_profit']):g}")
    if parsed.get("lot_size") is not None and len(bits) < 3:
        bits.append(f"{float(parsed['lot_size']):g} lot")
    if not bits:
        if _is_short_field_answer(text) and (
            draft.get("symbol") or draft.get("trade_type") or draft.get("entry_price") is not None
        ):
            return "Okay."
        return ""
    return "Got it — " + ", ".join(bits[:3]) + "."


def _shot_prompt(kind: str) -> str:
    if kind == "after":
        return "And the after chart?"
    return "Got a before-trade screenshot?"


def conversational_next(
    draft: Dict[str, Any],
    transcript: str,
    *,
    has_before: bool = False,
    has_after: bool = False,
    skip_screenshot: bool = False,
) -> Dict[str, Any]:
    """Next spoken line: acknowledge last answer, then one unfilled question."""
    hard = _hard_missing(draft, transcript)
    ack = _ack_from_last(transcript, draft)
    ask_shot = False
    shot_kind = ""
    complete = False
    if hard:
        q = dict(_QUESTIONS)[hard[0]]
        reply = f"{ack} {q}".strip() if ack else q
    elif not has_before and not skip_screenshot:
        q = _shot_prompt("before")
        reply = f"{ack} {q}".strip() if ack else q
        ask_shot = True
        shot_kind = "before"
        draft["screenshot_prompted"] = True
    elif not has_after and not skip_screenshot:
        reply = _shot_prompt("after")
        ask_shot = True
        shot_kind = "after"
        draft["screenshot_prompted"] = True
    else:
        reply = _spoken_wrap(draft)
        complete = required_ready(draft)
    draft.pop("_just_corrected", None)
    return {
        "reply": reply,
        "ask_screenshot": ask_shot,
        "screenshot_kind": shot_kind,
        "complete": complete,
    }


def guard_reply(
    reply: str,
    draft: Dict[str, Any],
    *,
    has_screenshot: bool = False,
    has_before: bool = False,
    has_after: bool = False,
    skip_screenshot: bool = False,
    transcript: str = "",
) -> str:
    """Force the next line to follow: one unfilled question, never a re-ask."""
    line = _one_question((reply or "").strip())
    hard = _hard_missing(draft, transcript)
    missing = missing_keys(draft)
    before = has_before or has_screenshot or bool(draft.get("screenshot_before"))
    after = has_after or bool(draft.get("screenshot_after"))
    if _asks_about_filled(line, draft) or not line:
        nxt = conversational_next(
            draft,
            transcript,
            has_before=before,
            has_after=after,
            skip_screenshot=skip_screenshot,
        )
        return nxt["reply"]
    if hard and _asks_about_filled(line, draft):
        return dict(_QUESTIONS)[hard[0]]
    if not line and missing:
        return dict(_QUESTIONS)[missing[0]]
    return line


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
            elif key == "voice_dump":
                prev = str(out.get("voice_dump") or "").strip()
                incoming_dump = str(val).strip()
                if not prev:
                    out[key] = incoming_dump[:8000]
                elif incoming_dump and incoming_dump not in prev:
                    out[key] = (prev + "\n" + incoming_dump).strip()[:8000]
                else:
                    out[key] = prev
            elif key == "thesis_notes":
                incoming_notes = str(val).strip()
                prev_notes = str(out.get("thesis_notes") or "").strip()
                if not prev_notes:
                    out[key] = incoming_notes[:2000]
                elif incoming_notes and _token_overlap(incoming_notes, prev_notes) >= 0.4:
                    # Same idea — keep the version that still looks like the user.
                    out[key] = (
                        incoming_notes[:2000]
                        if len(incoming_notes) >= len(prev_notes) * 0.7
                        else prev_notes
                    )
                else:
                    out[key] = prev_notes
            elif key in ("screenshot_prompted", "screenshot_before", "screenshot_after", "stop_skipped", "tp_skipped", "reflection_skipped", "lot_skipped"):
                if val:
                    out[key] = True
            elif key == "voice_mode":
                mode = str(val).strip().lower()
                if mode in ("quick", "full", ""):
                    out[key] = mode or None
            elif key == "followed_plan":
                plan = str(val).strip().lower()
                if plan in ("yes", "no", "mostly", "skipped"):
                    out[key] = plan
            elif key in ("feeling_during", "feeling_after", "lessons", "improve_next"):
                incoming_notes = str(val).strip()
                prev_notes = str(out.get(key) or "").strip()
                if not prev_notes:
                    out[key] = incoming_notes[:1200]
                elif incoming_notes and _token_overlap(incoming_notes, prev_notes) >= 0.35:
                    out[key] = (
                        incoming_notes[:1200]
                        if len(incoming_notes) >= len(prev_notes) * 0.7
                        else prev_notes
                    )
                else:
                    out[key] = prev_notes
            else:
                out[key] = val
        if src.get("screenshot_prompted"):
            out["screenshot_prompted"] = True
        if src.get("screenshot_before"):
            out["screenshot_before"] = True
        if src.get("screenshot_after"):
            out["screenshot_after"] = True
        if src.get("stop_skipped"):
            out["stop_skipped"] = True
        if src.get("tp_skipped"):
            out["tp_skipped"] = True
        if src.get("reflection_skipped"):
            out["reflection_skipped"] = True
        if src.get("lot_skipped"):
            out["lot_skipped"] = True
        if src.get("instrument_id"):
            out["instrument_id"] = src["instrument_id"]
        if src.get("voice_mode"):
            out["voice_mode"] = src["voice_mode"]
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
        bare = parsed["bare_number"]
        # Prefer size when that is the open gap (bare "0.5" after exit is known).
        need_lot = draft.get("lot_size") is None and not draft.get("lot_skipped")
        exit_known = draft.get("exit_price") is not None or incoming.get("exit_price") is not None
        facts_ready = (
            draft.get("entry_price") is not None
            and draft.get("stop_loss") is not None
            and (draft.get("status") or parsed.get("status"))
        )
        if need_lot and (exit_known or facts_ready) and 0 < float(bare) <= 100:
            # Small bare numbers after levels are usually lot size, not exit.
            levels = [
                draft.get("entry_price"),
                draft.get("stop_loss"),
                draft.get("take_profit"),
                draft.get("exit_price"),
            ]
            large_levels = [float(x) for x in levels if x is not None and float(x) > 100]
            if exit_known or large_levels or float(bare) <= 10:
                incoming["lot_size"] = bare
            elif incoming.get("exit_price") is None and (
                draft.get("status") == "closed" or parsed.get("status") == "closed"
            ):
                incoming["exit_price"] = bare
        elif incoming.get("entry_price") is None and draft.get("entry_price") is None:
            incoming["entry_price"] = bare
        elif incoming.get("stop_loss") is None and draft.get("stop_loss") is None and draft.get("entry_price"):
            incoming["stop_loss"] = bare
        elif incoming.get("take_profit") is None and draft.get("take_profit") is None and draft.get("stop_loss"):
            incoming["take_profit"] = bare
        elif (
            incoming.get("exit_price") is None
            and draft.get("exit_price") is None
            and (draft.get("status") == "closed" or parsed.get("status") == "closed")
        ):
            incoming["exit_price"] = bare
        elif need_lot and 0 < float(bare) <= 100:
            incoming["lot_size"] = bare
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
    if draft.get("stop_loss") is None and not draft.get("stop_skipped"):
        missing.append("stop_loss")
    status = draft.get("status")
    if not status:
        missing.append("status")
    if status == "closed" and draft.get("exit_price") is None:
        if draft.get("take_profit") is None:
            missing.append("take_profit")
        missing.append("exit_price")
    elif status == "open" and draft.get("take_profit") is None and not draft.get("tp_skipped"):
        missing.append("take_profit")
    if not draft.get("session_type"):
        missing.append("session_type")
    if not (draft.get("entry_time") or "").strip():
        missing.append("entry_time")
    if draft.get("lot_size") is None and not draft.get("lot_skipped"):
        missing.append("lot_size")
    if not draft.get("reflection_skipped"):
        thesis = (draft.get("thesis_notes") or "").strip()
        if not thesis or thesis == "skipped" or _levels_only_dump(thesis):
            missing.append("thesis_notes")
        if not draft.get("followed_plan"):
            missing.append("followed_plan")
        quick = (draft.get("voice_mode") or "") == "quick"
        if not quick:
            if not (draft.get("feeling_during") or "").strip():
                missing.append("feeling_during")
            if not (draft.get("feeling_after") or "").strip():
                missing.append("feeling_after")
            if not (draft.get("lessons") or "").strip():
                missing.append("lessons")
            if not (draft.get("improve_next") or "").strip():
                missing.append("improve_next")
    return missing


def journal_phase(draft: Dict[str, Any]) -> str:
    """Coarse progress for the Ink Bloom page: facts → reflect → charts → review."""
    hard = _hard_missing(draft)
    if any(k not in _REFLECT_KEYS for k in hard):
        return "facts"
    if any(k in _REFLECT_KEYS for k in hard):
        return "reflect"
    if not draft.get("screenshot_before") and not draft.get("screenshot_after") and not draft.get("screenshot_prompted"):
        return "charts"
    if draft.get("screenshot_prompted") and not (
        (draft.get("screenshot_before") and draft.get("screenshot_after"))
    ):
        return "charts"
    return "review"


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


def _mark_shots(
    draft: Dict[str, Any],
    text: str,
    *,
    has_before: bool,
    has_after: bool,
) -> Dict[str, Any]:
    t = (text or "").lower()
    if re.search(r"uploaded the after", t):
        has_after = True
    elif re.search(r"uploaded the before", t):
        has_before = True
    elif re.search(r"uploaded the chart", t):
        if draft.get("screenshot_before"):
            has_after = True
        else:
            has_before = True
    if has_before:
        draft["screenshot_before"] = True
        draft["screenshot_prompted"] = True
    if has_after:
        draft["screenshot_after"] = True
        draft["screenshot_prompted"] = True
    return draft


def _apply_spoken_extras(draft: Dict[str, Any], text: str) -> Dict[str, Any]:
    when = _extract_entry_time(text)
    if when and not draft.get("entry_time"):
        draft["entry_time"] = when
    if _skipped_time(text) and not draft.get("entry_time"):
        draft["entry_time"] = "unspecified"
    if _skipped_target(text):
        draft["tp_skipped"] = True
    if re.search(r"\b(no stop|without a stop|flat)\b", (text or "").lower()):
        draft["stop_skipped"] = True
    # Fill size when that is the open question (bare "0.5" / "half lot").
    hard = _hard_missing(draft, text)
    if hard and hard[0] == "lot_size" and draft.get("lot_size") is None:
        parsed = parse_voice_text(text)
        if parsed.get("lot_size") is not None:
            draft["lot_size"] = parsed["lot_size"]
        elif parsed.get("bare_number") is not None:
            n = float(parsed["bare_number"])
            if 0 < n <= 100:
                draft["lot_size"] = n
        elif re.search(r"\bhalf\s*lot\b", (text or "").lower()):
            draft["lot_size"] = 0.5
        elif re.search(r"\b(one|1)\s*lot\b", (text or "").lower()):
            draft["lot_size"] = 1.0
    return draft


def _apply_corrections(draft: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Overwrite a filled level when they change their mind mid-conversation."""
    if not _CORR_RE.search(text or ""):
        return draft
    parsed = parse_voice_text(text)
    incoming: Dict[str, Any] = {}
    t = (text or "").lower()
    for key in (
        "symbol",
        "trade_type",
        "entry_price",
        "stop_loss",
        "take_profit",
        "exit_price",
        "session_type",
        "status",
    ):
        if parsed.get(key) not in (None, "", []):
            incoming[key] = parsed[key]
    if parsed.get("bare_number") is not None:
        n = parsed["bare_number"]
        if re.search(r"\b(stop|sl)\b", t):
            incoming["stop_loss"] = n
        elif re.search(r"\b(target|tp|take profit)\b", t):
            incoming["take_profit"] = n
        elif re.search(r"\b(exit|got out)\b", t):
            incoming["exit_price"] = n
        else:
            incoming["entry_price"] = n
    if incoming:
        draft = merge_draft(draft, incoming)
        draft["_just_corrected"] = list(incoming.keys())
    return draft


def fallback_turn(
    transcript: str,
    draft: Optional[Dict[str, Any]] = None,
    *,
    has_screenshot: bool = False,
    has_before: bool = False,
    has_after: bool = False,
    session_hint: Optional[Dict[str, Any]] = None,
    skip_screenshot: bool = False,
) -> Dict[str, Any]:
    """Deterministic conversation when the LLM is unavailable."""
    draft = merge_draft(empty_draft(), draft)
    text = (transcript or "").strip()
    has_before = bool(has_before or has_screenshot or draft.get("screenshot_before"))
    has_after = bool(has_after or draft.get("screenshot_after"))
    if text:
        parsed = parse_voice_text(text)
        draft = apply_parse(draft, parsed)
        draft = _apply_corrections(draft, text)
        if _declines_shot(text, bool(draft.get("screenshot_prompted"))):
            skip_screenshot = True
        draft = _infer_closed_exit(draft, text)
        guessed, _ = normalize_symbol_guess(text)
        if guessed and not draft.get("symbol"):
            draft["symbol"] = guessed
        draft = _apply_spoken_extras(draft, text)
        draft = _mark_shots(draft, text, has_before=has_before, has_after=has_after)
        draft = _capture_user_words(draft, text)
        draft = _apply_reflection_answer(draft, text)

    has_before = bool(has_before or draft.get("screenshot_before"))
    has_after = bool(has_after or draft.get("screenshot_after"))
    nxt = conversational_next(
        draft,
        text,
        has_before=has_before,
        has_after=has_after,
        skip_screenshot=skip_screenshot,
    )
    _ = session_hint  # clock is a hint for the LLM only — never silently assumed
    return {
        "reply": nxt["reply"][:280],
        "draft": draft,
        "complete": nxt["complete"],
        "ask_screenshot": nxt["ask_screenshot"],
        "screenshot_kind": nxt["screenshot_kind"],
        "uncertain": [],
        "phase": journal_phase(draft),
        "source": "fallback",
    }


def _spoken_wrap(draft: Dict[str, Any]) -> str:
    bits = []
    if draft.get("trade_type") and draft.get("symbol"):
        side = "long" if draft["trade_type"] == "BUY" else "short"
        bits.append(f"{side} {draft['symbol']}")
    if draft.get("entry_price") is not None:
        bits.append(f"from {draft['entry_price']:g}")
    if draft.get("session_type"):
        bits.append(str(draft["session_type"]).replace(" Session", ""))
    state = "still open" if draft.get("status") != "closed" else "closed"
    core = " ".join(bits) if bits else "the trade"
    extra = ""
    metrics = _draft_metrics(draft)
    if draft.get("status") == "closed" and metrics.get("profit_loss") is not None:
        pnl = metrics["profit_loss"]
        extra = f" That’s about {pnl:+g}."
    elif metrics.get("rr_label"):
        extra = f" Planned {metrics['rr_label']}."
    elif metrics.get("sl_pips"):
        extra = f" Stop is {metrics['sl_pips']:g} away."
    return (
        f"Got it — {core}, {state}.{extra} "
        "I’ll put that in your journal — say save when it looks right."
    )


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
        "temperature": 0.2,
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
                        "already_captured": {
                            k: v
                            for k, v in (draft or {}).items()
                            if v not in (None, "", [])
                        },
                        "still_need": missing_keys(draft),
                        "verbatim_rule": (
                            "thesis_notes must be latest_user / recent user turns, "
                            "lightly cleaned at most. Never invent a different sentence."
                        ),
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
    llm_draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    if isinstance(llm_draft, dict):
        llm_draft = dict(llm_draft)
        llm_draft.pop("voice_dump", None)
        llm_draft.pop("screenshot_before", None)
        llm_draft.pop("screenshot_after", None)
        llm_draft.pop("screenshot_prompted", None)
        llm_draft.pop("entry_time", None)
    merged = merge_draft(draft, llm_draft)
    merged = _capture_user_words(merged, transcript, history)
    uncertain = data.get("uncertain") if isinstance(data.get("uncertain"), list) else []
    return {
        "draft": merged,
        "uncertain": [str(x) for x in uncertain if x][:8],
        "source": "llm",
    }


def run_turn(
    transcript: str,
    draft: Optional[Dict[str, Any]] = None,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    has_screenshot: bool = False,
    has_before: bool = False,
    has_after: bool = False,
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
            "screenshot_kind": "",
            "uncertain": [],
            "source": "fallback",
        }

    has_before = bool(has_before or has_screenshot or draft.get("screenshot_before"))
    has_after = bool(has_after or draft.get("screenshot_after"))
    parsed = parse_voice_text(text)
    seeded = apply_parse(draft, parsed)
    seeded = _apply_corrections(seeded, text)
    seeded = _infer_closed_exit(seeded, text)
    if _declines_shot(text, bool(seeded.get("screenshot_prompted"))):
        skip_screenshot = True
    seeded = _apply_spoken_extras(seeded, text)
    seeded = _mark_shots(seeded, text, has_before=has_before, has_after=has_after)
    seeded = _capture_user_words(seeded, text, history)
    seeded = _apply_reflection_answer(seeded, text)
    has_before = bool(has_before or seeded.get("screenshot_before"))
    has_after = bool(has_after or seeded.get("screenshot_after"))

    llm = _openai_turn(
        text,
        seeded,
        history or [],
        instruments or active_instrument_symbols(),
        session_hint,
        has_before and has_after,
    )
    merged = seeded
    source = "fallback"
    uncertain: List[Any] = []
    corr = list(seeded.get("_just_corrected") or [])
    if llm:
        merged = _capture_user_words(llm.get("draft") or seeded, text, history)
        merged = _apply_spoken_extras(merged, text)
        merged = _mark_shots(merged, text, has_before=has_before, has_after=has_after)
        merged = _apply_reflection_answer(merged, text)
        source = llm.get("source") or "llm"
        uncertain = llm.get("uncertain") or []
    if corr:
        merged["_just_corrected"] = corr

    nxt = conversational_next(
        merged,
        text,
        has_before=bool(has_before or merged.get("screenshot_before")),
        has_after=bool(has_after or merged.get("screenshot_after")),
        skip_screenshot=skip_screenshot,
    )
    return {
        "reply": nxt["reply"][:280],
        "draft": merged,
        "complete": nxt["complete"],
        "ask_screenshot": nxt["ask_screenshot"],
        "screenshot_kind": nxt["screenshot_kind"],
        "uncertain": uncertain,
        "phase": journal_phase(merged),
        "source": source,
    }


def draft_to_form_fields(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Map conversation draft onto the hidden Add Trade / guided fields."""
    tags = draft.get("setup_tags") or []
    emotions = draft.get("emotions") or []
    dump = (draft.get("voice_dump") or "").strip()
    thesis = (draft.get("thesis_notes") or "").strip()
    if thesis in ("skipped",):
        thesis = ""
    # Never replace a clean thesis with the full multi-turn dump.
    if not thesis and dump:
        for line in dump.split("\n"):
            low = line.lower()
            if _substantial_line(line) and any(
                h in low for h in ("because", "idea", "setup", "sweep", "break", "retest", "liquidity")
            ):
                thesis = line.strip()
                break
        if not thesis:
            thesis = dump.split("\n")[0].strip()
    status = draft.get("status") or ("closed" if draft.get("exit_price") is not None else "open")
    strategy = draft.get("strategy") or strategy_from_setups(tags)
    when = (draft.get("entry_time") or "").strip()
    if when and when != "unspecified" and when.lower() not in (thesis or "").lower():
        thesis = (thesis + " Entered around " + when + ".").strip() if thesis else ("Entered around " + when + ".")
    during = (draft.get("feeling_during") or "").strip()
    after = (draft.get("feeling_after") or "").strip()
    lessons = (draft.get("lessons") or "").strip()
    improve = (draft.get("improve_next") or "").strip()
    for skip_val in ("skipped",):
        if during == skip_val:
            during = ""
        if after == skip_val:
            after = ""
        if lessons == skip_val:
            lessons = ""
        if improve == skip_val:
            improve = ""
    followed = draft.get("followed_plan") or ""
    if followed == "skipped":
        followed = ""
    feeling_before = during or (emotions[0] if emotions else "")
    happened = lessons or ""
    emotion_line = ", ".join(
        [e for e in ([during, after] + list(emotions)) if e and e != "skipped"]
    )
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
        "guide_voice_dump": dump or thesis,
        "guide_emotions": emotion_line,
        "guide_feeling_before": feeling_before,
        "guide_feeling_after": after,
        "guide_followed_plan": followed,
        "guide_what_happened": happened,
        "guide_reflection": improve,
        "guide_setup_tags": ", ".join(tags),
        "pre_trade_plan": thesis,
        "post_trade_notes": "\n".join(
            [p for p in (happened, f"Feeling after: {after}" if after else "", f"Next time: {improve}" if improve else "") if p]
        ).strip(),
        "lessons_learned": improve or lessons,
        "from_guide": "1",
        "from_voice": "1",
    }
