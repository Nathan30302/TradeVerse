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
            "Rules-first playbook: (1) daily stop, (2) max open risk, (3) no trading after rule violation, (4) mandatory break after 2 losses.",
            "Account protection tactic: cap your total open risk so one spike cannot break daily drawdown.",
            "If you feel urgency (“I must pass today”), that’s your cue to reduce size and trade only A+ setups.",
        ),
        follow_ups=(
            "What daily loss rule should I use for my account size?",
            "How do I size trades to respect max drawdown?",
            "Give me a funded-account checklist I can follow every day.",
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
            "Separate risk from confidence: you can be ‘very confident’ and still risk the same 0.5R.",
            "Pre-trade risk check: (1) SL exists, (2) size computed, (3) worst-case day still survivable, (4) you’re not doubling after losses.",
            "Measure drawdown in R (not just $). A trader with stable R drawdown can scale; unstable R drawdown cannot.",
        ),
        follow_ups=(
            "Compute my position size from entry/SL and risk $.",
            "Give me a daily stop rule based on my last 30 trades.",
            "How do I avoid correlated risk across multiple trades?",
        ),
    ),
    KnowledgeTopic(
        key="expectancy",
        title="Expectancy: the math that decides if you’re profitable",
        triggers=("expectancy", "edge", "positive expectancy", "profit factor", "ev", "statistics", "math", "sample size"),
        bullets=(
            "Expectancy answers: ‘On average, what do I make per trade?’",
            "Core drivers: win rate, average win size, average loss size.",
            "High win rate can still lose money if losses are large and winners are small (and vice versa).",
            "Track results in R to compare trades across symbols and position sizes.",
            "If your average winner is < 1R and average loser is ~1R, you must maintain a very high win rate to stay profitable.",
            "Don’t judge your edge on tiny samples. Use consistent tagging and review in blocks (e.g., 20–50 trades).",
        ),
        follow_ups=(
            "How do I improve expectancy without increasing risk?",
            "How many trades do I need before trusting my stats?",
        ),
    ),
    KnowledgeTopic(
        key="rr_and_trade_management",
        title="R:R + trade management: stop giving back your edge",
        triggers=("take profit", "tp", "partial", "break even", "breakeven", "move stop", "trail", "trailing", "management", "hold winners"),
        bullets=(
            "Pick ONE management style and test it; random management creates random outcomes.",
            "Moving SL to breakeven too early often turns winners into scratches and kills expectancy.",
            "If you partial, define the rule: where, how much, and what happens to SL after.",
            "Use ‘invalidation’ instead of fear: if the reason for the trade is still valid, don’t micro-manage.",
            "Measure: average winner in R, average loser in R, and % scratches. That tells you if management helps.",
        ),
        follow_ups=(
            "Should I move to breakeven? Give me a rule.",
            "How do I stop cutting winners early?",
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
            "Use ‘if-then’ rules: if I take 2 losses → then I stop trading or reduce risk by 50%.",
            "Train boredom tolerance: many traders fail because they need action, not because they lack skill.",
            "Your job is to avoid self-sabotage during drawdown—size down and protect confidence.",
        ),
        follow_ups=(
            "Build me a cooldown rule after losses.",
            "How do I stop revenge trading in the moment?",
            "Give me a pre-trade mindset script.",
        ),
    ),
    KnowledgeTopic(
        key="process_checklist",
        title="A+ setup checklist: make your edge repeatable",
        triggers=("checklist", "a+", "setup", "entry trigger", "rules", "plan", "playbook", "conditions"),
        bullets=(
            "Define your market: which symbol(s), which session(s), which timeframe(s).",
            "Define one trigger: what must happen *right before* you enter (not ‘it looks good’).",
            "Define invalidation: what price action proves you wrong (your SL should reflect this).",
            "Define context filter: trend direction, key level, volatility state, or catalyst filter.",
            "Define risk: fixed risk per trade + daily stop + max open risk.",
            "Define post-trade rule: log result + one lesson in < 2 minutes.",
        ),
        follow_ups=(
            "Help me write my setup in one sentence.",
            "Build me a pre-trade checklist for breakout trades.",
        ),
    ),
    KnowledgeTopic(
        key="overtrading",
        title="Overtrading: fix it with rules, not willpower",
        triggers=("overtrade", "overtrading", "too many trades", "bored", "impulsive", "chasing"),
        bullets=(
            "Set a daily max trades limit (e.g., 2–3). When hit, stop.",
            "Use ‘A/B/C’ grading: only A setups allowed during drawdown; B/C are banned.",
            "Install a mandatory pause after every trade (e.g., 10 minutes) to break the loop.",
            "Remove chart-hopping: pick 1–2 markets and stay there.",
            "Replace action with review: if you want to click, review last trade and write the lesson first.",
        ),
        follow_ups=(
            "Give me an anti-overtrading rule for funded accounts.",
            "How do I build an A/B/C setup grading system?",
        ),
    ),
    KnowledgeTopic(
        key="drawdown_recovery",
        title="Drawdown recovery: stabilize before you ‘make it back’",
        triggers=("drawdown", "dd", "recover", "lost money", "blown", "down bad", "losing streak"),
        bullets=(
            "Step 1: reduce risk immediately (often 50%) until stability returns.",
            "Step 2: trade fewer—only A+ setups—until rule violations drop to near zero.",
            "Step 3: review the last 10 trades and label the cause: (a) bad selection, (b) bad execution, (c) bad management, (d) random variance.",
            "Step 4: one fix only (one rule). Many traders fail by changing everything.",
            "Step 5: re-scale slowly after 2–4 clean weeks, not after one good day.",
        ),
        follow_ups=(
            "How do I diagnose if my losses are variance or a broken edge?",
            "Give me a drawdown protocol I can follow.",
        ),
    ),
    KnowledgeTopic(
        key="market_structure",
        title="Market structure (practical): trade with the dominant story",
        triggers=("structure", "market structure", "trend", "range", "break of structure", "bos", "choch"),
        bullets=(
            "Identify regime: trend or range. Don’t use a trend playbook in a range.",
            "Trend basics: higher highs/higher lows (uptrend), lower lows/lower highs (downtrend).",
            "In ranges: fade extremes with clear invalidation or wait for a clean breakout + retest.",
            "Pick one timeframe for context (higher) and one for execution (lower).",
            "Write the ‘story’ in one line before entry: ‘trend is up, pullback to key level, trigger is X.’",
        ),
        follow_ups=(
            "How do I pick my context timeframe?",
            "Give me a structure checklist for entries.",
        ),
    ),
    KnowledgeTopic(
        key="liquidity_and_volatility",
        title="Liquidity + volatility: stop trading in the worst conditions",
        triggers=("liquidity", "volatility", "spread", "slippage", "news", "cpi", "nfp", "fomc"),
        bullets=(
            "If spreads widen or candles spike, your stop size needs to reflect that or you’ll get churned.",
            "Avoid major news windows unless you have a tested news playbook.",
            "Use a volatility filter: if today’s range is extreme, reduce size or wait for structure to settle.",
            "Session matters: many markets move best in specific hours; outside that window, signals degrade.",
            "If you can’t explain the current volatility state, don’t size up.",
        ),
        follow_ups=(
            "Should I trade during news? Give me rules.",
            "How do I adapt SL/TP to volatility?",
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
            "Scale via frequency before size: first prove you can repeat A+ setups; then increase risk slowly.",
            "Keep a ‘revert rule’: if you hit X drawdown at new size, revert instantly—no debate.",
        ),
        follow_ups=(
            "When should I size up based on my stats?",
            "Make me a scaling checklist for the next 4 weeks.",
            "How do I avoid blowing up after a good streak?",
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
            "Use a ‘mistake taxonomy’: selection, execution, management, psychology. You can’t fix what you can’t name.",
            "Review in blocks: look at the last 20 trades of one strategy; avoid mixing everything.",
        ),
        follow_ups=(
            "Give me a minimal journaling template I can follow daily.",
            "What should my one rule be next week based on my week?",
            "How do I run a weekly review in 20 minutes?",
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

