"""
Web-enabled AI helper (OpenAI + Tavily).

This is optional: if keys are not configured, callers should fall back to local AIAnalyzer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import os
import random
import time

import requests


class OpenAIRateLimited(Exception):
    """Raised when OpenAI returns 429 after retries (callers should fall back quietly)."""


@dataclass(frozen=True)
class WebAIResult:
    answer: str
    follow_ups: List[str]


def _tavily_search(query: str, *, max_results: int = 5, timeout_s: int = 10) -> List[Dict[str, Any]]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(int(max_results), 8)),
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    data = resp.json() or {}
    results = data.get("results") or []
    if not isinstance(results, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in results[:8]:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "title": (r.get("title") or "")[:140],
                "url": (r.get("url") or "")[:500],
                "content": (r.get("content") or "")[:1200],
            }
        )
    return out


def _retry_after_seconds(resp: requests.Response, attempt: int) -> float:
    """Parse Retry-After or use bounded exponential backoff (seconds)."""
    raw = (resp.headers.get("Retry-After") or "").strip()
    if raw:
        try:
            return min(max(float(raw), 0.5), 25.0)
        except ValueError:
            pass
    # jitter reduces thundering herd when many workers hit 429 together
    base = min(2.0**attempt, 12.0)
    return base + random.uniform(0.0, 0.75)


def _openai_chat(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    timeout_s: int = 20,
    max_retries: int = 4,
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    last_resp: requests.Response | None = None
    for attempt in range(max_retries):
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        last_resp = resp
        if resp.status_code == 429:
            if attempt + 1 >= max_retries:
                break
            delay = _retry_after_seconds(resp, attempt)
            time.sleep(delay)
            continue
        if resp.status_code in (500, 502, 503, 504):
            if attempt + 1 >= max_retries:
                break
            time.sleep(_retry_after_seconds(resp, attempt))
            continue
        resp.raise_for_status()
        data = resp.json() or {}
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}
        return str(msg.get("content") or "")

    if last_resp is not None and last_resp.status_code == 429:
        raise OpenAIRateLimited("OpenAI rate limit (429) after retries")
    if last_resp is not None:
        last_resp.raise_for_status()
    return ""


def answer_with_web(
    *,
    question: str,
    user_context: str,
    history: Optional[List[Dict[str, str]]] = None,
    is_personal: bool = False,
    allow_web_search: bool = True,
) -> WebAIResult:
    """
    Ask OpenAI to answer. Personal journal questions use evidence-only grounding
    (no web search). General questions may use Tavily summaries.
    """
    q = (question or "").strip()
    if not q:
        return WebAIResult(answer="Ask a question and I’ll help.", follow_ups=[])

    results: List[Dict[str, Any]] = []
    if allow_web_search and not is_personal:
        results = _tavily_search(q, max_results=5)
    sources_txt = ""
    if results:
        sources_txt = "\n\nWeb sources (summaries):\n" + "\n".join(
            [f"- {r.get('title','').strip()} — {r.get('url','').strip()}\n  {r.get('content','').strip()}" for r in results]
        )

    hist = history or []
    hist_lines: List[str] = []
    for m in hist[-8:]:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role and content:
            hist_lines.append(f"{role.upper()}: {content}")
    hist_txt = ("\n\nConversation context:\n" + "\n".join(hist_lines)) if hist_lines else ""

    if is_personal:
        system = (
            "You are TradeVerse AI Buddy: a personal trading coach inside a trading journal.\n"
            "EVIDENCE-ONLY MODE for this question:\n"
            "1) Answer using ONLY the User context block (stats, focus rule, playbook adherence, plans, snippets).\n"
            "2) Cite specific numbers from context (win rate, P/L, compliance counts). Never invent trades or P/L.\n"
            "3) If context lacks the answer, say what data is missing and give one logging action — do not guess.\n"
            "4) Be practical and risk-first: end with ONE concrete next-week rule the trader can follow.\n"
            "5) Keep it concise: short paragraphs or bullets. No generic trading lectures.\n"
        )
        personal_note = (
            "This is about the user's own journal. Do not use outside market knowledge. "
            "Prioritize focus compliance and playbook adherence when present.\n"
        )
    else:
        system = (
            "You are TradeVerse AI Buddy: a professional trading coach inside a trading journal app.\n"
            "Rules:\n"
            "1) Answer the user's exact question first — do not change the topic or give a generic lecture.\n"
            "2) When user context includes journal stats, cite those numbers; never invent trades or P/L.\n"
            "3) Be practical, risk-first, and concise (bullets + one clear next action).\n"
            "4) For general education you may use web source summaries; do not hallucinate live prices or news.\n"
            "5) If you cannot answer from context/sources, say what is missing and ask one clarifying question.\n"
        )
        personal_note = ""
    user = (
        f"User context:\n{user_context}\n"
        f"{hist_txt}\n\n"
        f"{personal_note}"
        f"Question: {q}\n"
        f"{sources_txt}\n\n"
        "Structure: (1) Direct answer to the question, (2) 2–4 bullet points, (3) one next action.\n"
        "End with 2 short follow-up questions the user can tap next."
    )

    content = _openai_chat(system, user)
    content = (content or "").strip()
    if not content:
        return WebAIResult(answer="", follow_ups=[])

    # Lightweight follow-up extraction: last two lines starting with '?' or bullets.
    follow_ups: List[str] = []
    for line in reversed(content.splitlines()):
        t = line.strip().lstrip("-•").strip()
        if t.endswith("?") and len(t) <= 120:
            follow_ups.append(t)
        if len(follow_ups) >= 2:
            break
    follow_ups.reverse()
    return WebAIResult(answer=content, follow_ups=follow_ups)

