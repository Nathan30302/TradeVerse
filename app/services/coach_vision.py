"""
OpenAI vision helper — analyze trade screenshots / charts for AI Coach.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import os
import random
import time

import requests

from app.services.web_ai import OpenAIRateLimited, WebAIResult, _retry_after_seconds


def analyze_chart_image(
    *,
    question: str,
    user_context: str,
    image_data_url: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> WebAIResult:
    """
    Coach analysis of a chart/screenshot. Never invent live prices or give buy/sell signals.
    image_data_url: full data URL (data:image/png;base64,...) or https URL.
    """
    from app.services.ai_buddy_voice import SYSTEM_PERSONAL, USER_STRUCTURE_HINT

    q = (question or "").strip() or "Analyze this chart screenshot from my journal perspective."
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return WebAIResult(answer="", follow_ups=[])

    hist_lines = []
    for m in (history or [])[-6:]:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role and content:
            hist_lines.append(f"{role.upper()}: {content[:400]}")
    hist_txt = ("\nConversation:\n" + "\n".join(hist_lines)) if hist_lines else ""

    system = (
        SYSTEM_PERSONAL
        + "\n\nYou are looking at a trader’s chart or trade screenshot. "
        "Identify strengths, mistakes, and improvement areas across technical, psychology, and risk. "
        "Never give entry/exit signals or predict where price will go. "
        "If the image is unclear, say what you need."
    )
    user_text = (
        f"User journal context:\n{user_context}\n{hist_txt}\n\n"
        f"Trader question: {q}\n\n{USER_STRUCTURE_HINT}"
    )

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }

    last_resp = None
    content = ""
    for attempt in range(4):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            last_resp = resp
            if resp.status_code == 429:
                if attempt + 1 >= 4:
                    raise OpenAIRateLimited("vision 429")
                time.sleep(_retry_after_seconds(resp, attempt))
                continue
            if resp.status_code in (500, 502, 503, 504):
                time.sleep(_retry_after_seconds(resp, attempt))
                continue
            resp.raise_for_status()
            data = resp.json() or {}
            choices = data.get("choices") or []
            if choices:
                msg = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}
                content = str(msg.get("content") or "").strip()
            break
        except OpenAIRateLimited:
            raise
        except requests.RequestException:
            if attempt + 1 >= 4:
                return WebAIResult(answer="", follow_ups=[])
            time.sleep(1.0 + random.uniform(0, 0.5))

    if not content:
        return WebAIResult(answer="", follow_ups=[])

    follow_ups: List[str] = []
    for line in reversed(content.splitlines()):
        t = line.strip().lstrip("-•").strip()
        if t.endswith("?") and len(t) <= 120:
            follow_ups.append(t)
        if len(follow_ups) >= 2:
            break
    follow_ups.reverse()
    return WebAIResult(answer=content, follow_ups=follow_ups)
