"""
Trading knowledge base (original, non-quoted).

Goal: provide AI Buddy with broad, professional trading coaching guidance without
requiring external web/LLM services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class KnowledgeTopic:
    key: str
    title: str
    triggers: Tuple[str, ...]
    bullets: Tuple[str, ...]
    follow_ups: Tuple[str, ...]


TOPICS: List[KnowledgeTopic] = [
    KnowledgeTopic(
        key="funded_accounts",
        title="Funded accounts: survive the rules first",
        triggers=("funded", "prop", "prop firm", "evaluation", "challenge", "drawdown", "daily drawdown", "max loss"),
        bullets=(
            "Treat the rules as the strategy: your edge is worthless if you violate limits.",
            "Use an R-based risk plan: pick a daily stop (e.g., −2R) and never override it.",
            "Size down until your worst day is survivable: most blowups are sizing + overtrading, not bad setups.",
            "Avoid ‘revenge sequences’: after a loss, reduce size or require a higher-quality trigger before re-entry.",
            "Track rule violations as a separate metric (they predict failure more than win rate).",
        ),
        follow_ups=(
            "What daily loss rule should I use for my account size?",
            "How do I size trades to respect max drawdown?",
        ),
    ),
    KnowledgeTopic(
        key="risk_management",
        title="Risk management: the non-negotiables",
        triggers=("risk", "position size", "lot", "stop loss", "sl", "drawdown", "dd", "lose", "loss limit"),
        bullets=(
            "Pick one risk unit and stick to it (R). Define 1R as the $ you lose if SL is hit.",
            "Keep risk per trade boring (often 0.25–1.0%). Consistency beats excitement.",
            "Have a daily stop: either a money stop or an R stop. If hit, stop trading.",
            "Avoid correlated exposure: multiple trades on the same theme can be one big bet.",
            "Never widen SL to avoid being wrong; if your idea is invalidated, you’re done.",
        ),
        follow_ups=(
            "Compute my position size from entry/SL and risk $.",
            "Give me a daily stop rule based on my last 30 trades.",
        ),
    ),
    KnowledgeTopic(
        key="psychology",
        title="Trader psychology: control the process, not the outcome",
        triggers=("psychology", "discipline", "emotion", "revenge", "fomo", "fear", "greed", "tilt", "confidence"),
        bullets=(
            "Your goal is not to win today—your goal is to execute your plan cleanly.",
            "Separate ‘good trade’ from ‘winning trade’: a good trade is one that followed your rules.",
            "Name the emotion before you click: labeling reduces impulsive behavior.",
            "Install friction: checklists, timeouts after losses, and ‘one more filter’ on entries.",
            "Review the story you tell yourself after a loss; most overtrading is a narrative problem.",
        ),
        follow_ups=(
            "Build me a cooldown rule after losses.",
            "How do I stop revenge trading in the moment?",
        ),
    ),
    KnowledgeTopic(
        key="scaling",
        title="Scaling up: earn the right to size up",
        triggers=("scale", "scaling", "increase size", "bigger size", "consistency", "growth", "level up"),
        bullets=(
            "Scale only after process stability: low rule-violations, stable R distribution, and predictable drawdowns.",
            "Increase size in small steps (e.g., +10–20%) and keep the same daily stop in R.",
            "If your drawdown grows faster than your returns after sizing up, revert immediately.",
            "Avoid changing strategy and size at the same time—change one variable only.",
            "Define ‘promotion criteria’: e.g., 4 clean weeks + no revenge sequences + max DD below threshold.",
        ),
        follow_ups=(
            "When should I size up based on my stats?",
            "Make me a scaling checklist for the next 4 weeks.",
        ),
    ),
    KnowledgeTopic(
        key="habits_journaling",
        title="Habits + journaling: your compounding advantage",
        triggers=("journal", "journaling", "habit", "routine", "review", "process", "plan", "checklist"),
        bullets=(
            "Journal the decision, not just the outcome: entry reason, invalidation, and risk plan.",
            "Write a 2-minute post-trade: what was correct, what was sloppy, what’s the fix.",
            "Weekly review: one leak → one rule. Don’t add five rules; add one that sticks.",
            "Tag trades consistently (strategy/session/emotion) so patterns are measurable.",
            "Build a ‘personal playbook’ page: your A+ setup definition + screenshots + rules.",
        ),
        follow_ups=(
            "Give me a minimal journaling template I can follow daily.",
            "What should my one rule be next week based on my week?",
        ),
    ),
]


def match_topic(question_lower: str) -> KnowledgeTopic | None:
    q = (question_lower or "").lower()
    for t in TOPICS:
        if any(k in q for k in t.triggers):
            return t
    return None


def render_topic(topic: KnowledgeTopic) -> Tuple[str, List[str]]:
    answer = topic.title + "\n" + "\n".join([f"- {b}" for b in topic.bullets])
    return answer, list(topic.follow_ups)

