"""
Owner setup coach — screenshot go / wait / no against the active strategy rules.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests
from flask import current_app

from app.services.chart_extract import _file_to_data_url, _parse_json_object


def _strategy_rulebook_text(strategy) -> str:
    """Compact rule pack for the vision model."""
    if not strategy:
        return "No active strategy."
    parts = [
        f"SYSTEM: {strategy.name}",
        f"STYLE: {strategy.style or ''}",
        f"OVERVIEW: {(strategy.overview or '')[:1200]}",
        f"WEEKLY: {(strategy.weekly_bias_rules or '')[:600]}",
        f"DAILY: {(strategy.daily_bias_rules or '')[:600]}",
        f"H4: {(strategy.h4_rules or '')[:500]}",
        f"ENTRY TF: {(strategy.m15_rules or '')[:500]}",
        f"ENTRY RULES: {(strategy.entry_rules or '')[:900]}",
        f"DO NOT TRADE: {(strategy.do_not_trade_rules or '')[:700]}",
        f"INVALIDATION: {(strategy.invalidation_rules or '')[:400]}",
        f"MIN R:R: {getattr(strategy, 'min_rr', 2)}",
    ]
    try:
        checklist = json.loads(strategy.checklist_json or "{}")
    except (TypeError, json.JSONDecodeError):
        checklist = {}
    pre = checklist.get("pre_trade") or []
    if pre:
        parts.append(
            "PRE-TRADE CHECKLIST:\n"
            + "\n".join(f"- {item.get('label')}" for item in pre if isinstance(item, dict))
        )
    return "\n\n".join(p for p in parts if p and not p.endswith(": "))


def analyze_setup_screenshots(
    *,
    strategy,
    images: List[Any],
    notes: str = "",
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Nathan drops 1–3 chart screenshots (e.g. Daily / 4H / entry TF).
    Returns structured coaching: go | wait | no_trade.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "configured": False,
            "verdict": "wait",
            "headline": "Screenshot coach needs OPENAI_API_KEY on the server.",
            "reasons": [],
            "wait_for": ["Configure vision key, or walk the ritual checklist manually."],
            "checklist_hits": [],
            "checklist_misses": [],
            "error": "Vision not configured.",
        }

    data_urls: List[str] = []
    for fs in images[:3]:
        url = _file_to_data_url(fs)
        if url:
            data_urls.append(url)
    if not data_urls:
        return {
            "ok": False,
            "configured": True,
            "verdict": "wait",
            "headline": "Could not read those images.",
            "reasons": [],
            "wait_for": ["Upload clear PNG/JPEG chart screenshots (Daily, 4H, entry)."],
            "checklist_hits": [],
            "checklist_misses": [],
            "error": "No readable images.",
        }

    rules = _strategy_rulebook_text(strategy)
    system = (
        "You are Nathan's private trading rules referee for ONE named strategy. "
        "You judge setups ONLY against the provided rulebook — never invent a different system. "
        "Look at the chart screenshot(s). Decide if this is a valid entry NOW. "
        "Respond with JSON only:\n"
        "{"
        '"verdict":"go"|"wait"|"no_trade",'
        '"headline":"short plain sentence",'
        '"reasons":["..."],'
        '"wait_for":["specific next condition to wait for — empty if go"],'
        '"checklist_hits":["rule labels that appear satisfied"],'
        '"checklist_misses":["rule labels missing or violated"],'
        '"timeframes_seen":["guess which TF each image shows"],'
        '"confidence":0.0'
        "}\n"
        "Rules:\n"
        "- go = every mandatory pre-trade condition looks present; still remind min R:R / SL.\n"
        "- wait = structure/direction OK but entry trigger incomplete — list exact waits.\n"
        "- no_trade = conflicts with Do-Not-Trade or HTF sync / mid-air / chase / wrong side.\n"
        "- Never invent live prices. If image is unclear, verdict=wait and say what screenshot is needed.\n"
        "- Be strict. Prefer wait over go."
    )
    user_bits = [
        f"Active strategy rulebook:\n{rules}",
        f"Trader notes: {(notes or 'none')[:500]}",
        f"Symbol hint: {(symbol or 'unknown')[:40]}",
        f"Images attached: {len(data_urls)} (prefer Weekly/Daily, then 4H, then entry TF).",
        "Judge this setup now.",
    ]
    content: List[Dict[str, Any]] = [{"type": "text", "text": "\n\n".join(user_bits)}]
    for url in data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    model = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=75,
        )
    except requests.RequestException as exc:
        try:
            current_app.logger.warning("owner setup coach request failed: %s", exc)
        except Exception:
            pass
        return {
            "ok": False,
            "configured": True,
            "verdict": "wait",
            "headline": "Coach could not reach vision just now.",
            "reasons": [],
            "wait_for": ["Retry in a minute, or walk the ritual by hand."],
            "checklist_hits": [],
            "checklist_misses": [],
            "error": "request_failed",
        }

    if resp.status_code != 200:
        try:
            current_app.logger.warning("owner setup coach HTTP %s: %s", resp.status_code, resp.text[:240])
        except Exception:
            pass
        return {
            "ok": False,
            "configured": True,
            "verdict": "wait",
            "headline": "Screenshot coach failed — use the ritual checklist.",
            "reasons": [],
            "wait_for": [],
            "checklist_hits": [],
            "checklist_misses": [],
            "error": f"http_{resp.status_code}",
        }

    data = resp.json() or {}
    choices = data.get("choices") or []
    raw = ""
    if choices:
        msg = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}
        raw = str(msg.get("content") or "").strip()
    parsed = _parse_json_object(raw)
    verdict = str(parsed.get("verdict") or "wait").strip().lower()
    if verdict not in ("go", "wait", "no_trade"):
        verdict = "wait"

    def _str_list(key: str) -> List[str]:
        val = parsed.get(key) or []
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if str(x).strip()][:12]

    return {
        "ok": True,
        "configured": True,
        "verdict": verdict,
        "headline": str(parsed.get("headline") or "Review the checklist.")[:280],
        "reasons": _str_list("reasons"),
        "wait_for": _str_list("wait_for"),
        "checklist_hits": _str_list("checklist_hits"),
        "checklist_misses": _str_list("checklist_misses"),
        "timeframes_seen": _str_list("timeframes_seen"),
        "confidence": float(parsed.get("confidence") or 0) if _is_number(parsed.get("confidence")) else None,
        "error": None,
        "strategy_name": getattr(strategy, "name", None),
    }


def _is_number(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def practice_plan_for(strategy) -> Dict[str, Any]:
    """Extract daily practice block from strategy checklist JSON."""
    try:
        data = json.loads(getattr(strategy, "checklist_json", None) or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    practice = data.get("practice") if isinstance(data, dict) else None
    if isinstance(practice, dict) and practice.get("blocks"):
        return practice
    return default_practice_plan(getattr(strategy, "name", None) or "your system")


def ritual_for(strategy) -> List[Dict[str, str]]:
    try:
        data = json.loads(getattr(strategy, "checklist_json", None) or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    ritual = data.get("ritual") if isinstance(data, dict) else None
    if isinstance(ritual, list) and ritual:
        return [x for x in ritual if isinstance(x, dict)]
    # Fall back to states as ritual
    states = data.get("states") if isinstance(data, dict) else None
    if isinstance(states, list) and states:
        return [
            {
                "id": s.get("id") or f"s{i}",
                "title": s.get("title") or f"Step {i}",
                "do": s.get("prompt") or "",
                "pass": "Only continue when this is clearly true.",
            }
            for i, s in enumerate(states, 1)
            if isinstance(s, dict)
        ]
    return []


def default_practice_plan(name: str) -> Dict[str, Any]:
    return {
        "duration_minutes": 120,
        "title": f"Daily 2-hour practice — {name}",
        "focus": "Reps beat motivation. Same drills every day.",
        "blocks": [
            {
                "minutes": 20,
                "title": "Map the board",
                "tasks": [
                    "Mark higher-timeframe bias with bodies only.",
                    "Write one sentence: bullish, bearish, or no trade — and why.",
                ],
            },
            {
                "minutes": 40,
                "title": "Replay drills",
                "tasks": [
                    "Replay 5 historical charts. Mark levels before revealing the outcome.",
                    "Score yourself: valid setup or pass.",
                ],
            },
            {
                "minutes": 40,
                "title": "Live watch (or sim)",
                "tasks": [
                    "Watch for one A+ setup only. If nothing, log a clean no-trade.",
                    "Screenshot candidates and run them through the setup coach.",
                ],
            },
            {
                "minutes": 20,
                "title": "Review",
                "tasks": [
                    "Write what you waited for that never came.",
                    "Log any rule you almost broke.",
                ],
            },
        ],
    }
