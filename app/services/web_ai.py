"""
Web-enabled AI helper (OpenAI + Tavily).

This is optional: if keys are not configured, callers should fall back to local AIAnalyzer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import os
import requests


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
    resp = requests.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()
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


def _openai_chat(system: str, user: str, *, model: str = "gpt-4o-mini", timeout_s: int = 20) -> str:
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
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json() or {}
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}
    return str(msg.get("content") or "")


def answer_with_web(
    *,
    question: str,
    user_context: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> WebAIResult:
    """
    Use Tavily search results as additional context and ask OpenAI to answer.
    Returns an answer and follow-ups; callers should handle exceptions and fallback.
    """
    q = (question or "").strip()
    if not q:
        return WebAIResult(answer="Ask a question and I’ll help.", follow_ups=[])

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

    system = (
        "You are TradeVerse AI Buddy: a professional trading coach.\n"
        "Be practical, risk-first, and tailored to the user's stats.\n"
        "If the question asks for general trading knowledge, you may use web sources.\n"
        "Do not hallucinate prices/news. If sources are thin, say so.\n"
        "Keep answers concise with bullets and a clear next action.\n"
    )
    user = (
        f"User context:\n{user_context}\n"
        f"{hist_txt}\n\n"
        f"Question: {q}\n"
        f"{sources_txt}\n\n"
        "Answer as a coach. End with 2 follow-up questions the user can ask next."
    )

    content = _openai_chat(system, user)
    content = (content or "").strip()
    if not content:
        return WebAIResult(answer="I couldn’t generate an answer right now. Try again.", follow_ups=[])

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

