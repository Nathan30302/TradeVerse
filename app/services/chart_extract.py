"""
Best-effort structured extraction of trade levels from a chart screenshot.

Never silently overwrite prices — callers must confirm every numeric field.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

from flask import current_app


_EXTRACT_SYSTEM = (
    "You extract trading journal fields from a broker or TradingView screenshot. "
    "Return ONLY compact JSON. If a value is not clearly visible, use null. "
    "Never invent prices. Prefer the actual numbers printed on the chart or ticket. "
    "Keys: symbol (string like EURUSD or XAUUSD), trade_type (BUY or SELL), "
    "entry_price (number), stop_loss (number), take_profit (number), "
    "exit_price (number), timeframe (string like 15M), lot_size (number), "
    "confidence (0-1). Include a short 'notes' string of what you saw."
)


def _file_to_data_url(file_storage, max_bytes: int = 4_000_000) -> Optional[str]:
    if not file_storage:
        return None
    raw = file_storage.read(max_bytes + 1)
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass
    if not raw or len(raw) > max_bytes:
        return None
    mime = (getattr(file_storage, "mimetype", None) or "image/jpeg").split(";")[0].strip()
    if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        mime = "image/jpeg"
    import base64

    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _clean_number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_trade_from_image(file_storage) -> Dict[str, Any]:
    """
    Return extracted fields plus which ones need confirmation.

    {ok, configured, fields, uncertain, notes, error}
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "configured": False,
            "fields": {},
            "uncertain": [],
            "notes": "",
            "error": "Screenshot reading is not configured. You can still type or speak the levels.",
        }

    data_url = _file_to_data_url(file_storage)
    if not data_url:
        return {
            "ok": False,
            "configured": True,
            "fields": {},
            "uncertain": [],
            "notes": "",
            "error": "Could not read that image. Try a PNG or JPEG screenshot.",
        }

    payload = {
        "model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the trade ticket / chart levels. JSON only.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("chart extract request failed: %s", exc)
        return {
            "ok": False,
            "configured": True,
            "fields": {},
            "uncertain": [],
            "notes": "",
            "error": "Could not read the screenshot just now. Continue and confirm the numbers.",
        }

    if resp.status_code != 200:
        current_app.logger.warning("chart extract HTTP %s: %s", resp.status_code, resp.text[:240])
        return {
            "ok": False,
            "configured": True,
            "fields": {},
            "uncertain": [],
            "notes": "",
            "error": "Screenshot reading failed. Confirm the levels yourself.",
        }

    try:
        body = resp.json()
        content = (((body.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    except (ValueError, AttributeError, IndexError):
        content = ""

    parsed = _parse_json_object(content)
    fields: Dict[str, Any] = {}
    uncertain = []

    sym = (parsed.get("symbol") or "").strip().upper().replace("/", "")
    if sym and 3 <= len(sym) <= 12:
        fields["symbol"] = re.sub(r"[^A-Z0-9]", "", sym)
        uncertain.append("symbol")

    side = str(parsed.get("trade_type") or parsed.get("side") or "").strip().upper()
    if side in ("BUY", "SELL", "LONG", "SHORT"):
        fields["trade_type"] = "SELL" if side in ("SELL", "SHORT") else "BUY"
        uncertain.append("trade_type")

    for src, dest in (
        ("entry_price", "entry_price"),
        ("stop_loss", "stop_loss"),
        ("take_profit", "take_profit"),
        ("exit_price", "exit_price"),
        ("lot_size", "lot_size"),
    ):
        num = _clean_number(parsed.get(src))
        if num is not None:
            fields[dest] = num
            uncertain.append(dest)

    tf = str(parsed.get("timeframe") or "").strip().upper()
    if tf and len(tf) <= 8:
        fields["timeframe"] = tf.replace("MIN", "M").replace("MINUTE", "M")

    notes = str(parsed.get("notes") or "").strip()[:400]
    conf = parsed.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0
    if conf_f >= 0.85:
        # Still confirm prices — never silent — but drop symbol/side from uncertain
        # if the model is very sure AND values look like real tickets.
        uncertain = [u for u in uncertain if u in ("entry_price", "stop_loss", "take_profit", "exit_price", "lot_size")]

    return {
        "ok": bool(fields),
        "configured": True,
        "fields": fields,
        "uncertain": uncertain,
        "notes": notes,
        "confidence": conf_f,
        "error": None if fields else "No trade levels were readable in that screenshot.",
    }
