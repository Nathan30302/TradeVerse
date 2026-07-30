"""
Deterministic per-trade coach grades (psychology, execution, risk, etc.).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

LETTER_SCALE = (
    (95, "A+"),
    (88, "A"),
    (80, "B"),
    (70, "C"),
    (55, "D"),
    (0, "F"),
)

NEGATIVE_EMOTIONS = {
    "revenge",
    "revenge trading",
    "fomo",
    "angry",
    "greedy",
    "frustrated",
    "anxious",
    "fearful",
    "tilt",
}


def _letter(score: float) -> str:
    s = max(0.0, min(100.0, float(score)))
    for threshold, letter in LETTER_SCALE:
        if s >= threshold:
            return letter
    return "F"


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, n))


def grade_trade(trade) -> Dict[str, Any]:
    """
    Grade a closed trade across coaching dimensions using journal fields only.
    Returns letters + short reasons + overall.
    """
    dimensions: List[Tuple[str, float, str]] = []

    # Risk management
    has_sl = getattr(trade, "stop_loss", None) is not None or getattr(trade, "risk_amount", None) is not None
    rr = getattr(trade, "risk_reward", None)
    risk_score = 40.0
    risk_why = "No stop or risk amount logged."
    if has_sl:
        risk_score = 78.0
        risk_why = "Stop / risk defined."
        if rr is not None:
            try:
                rrf = float(rr)
                if rrf >= 1.5:
                    risk_score = 92.0
                    risk_why = f"Risk defined with planned R:R {rrf:.2f}."
                elif rrf >= 1.0:
                    risk_score = 82.0
                    risk_why = f"Risk defined; R:R {rrf:.2f} is acceptable."
                else:
                    risk_score = 62.0
                    risk_why = f"Risk defined but R:R {rrf:.2f} is thin."
            except (TypeError, ValueError):
                pass
    dimensions.append(("risk", risk_score, risk_why))

    # Rule adherence / playbook
    followed = bool(getattr(trade, "playbook_followed", False))
    checklist = bool(getattr(trade, "checklist_completed", False))
    rule_score = 55.0
    if followed and checklist:
        rule_score = 92.0
        rule_why = "Playbook followed and checklist completed."
    elif followed:
        rule_score = 80.0
        rule_why = "Playbook marked followed."
    elif checklist:
        rule_score = 72.0
        rule_why = "Checklist completed; playbook not marked followed."
    else:
        rule_why = "Playbook / checklist not confirmed on this trade."
    dimensions.append(("rules", rule_score, rule_why))

    # Psychology
    emo = (getattr(trade, "emotion", None) or "").strip()
    emo_l = emo.lower()
    psych_score = 70.0
    if not emo:
        psych_why = "No emotion tagged — psychology grade is incomplete."
        psych_score = 58.0
    elif emo_l in NEGATIVE_EMOTIONS or any(x in emo_l for x in ("revenge", "fomo", "tilt", "greed")):
        psych_score = 42.0
        psych_why = f"Emotion tagged {emo} — high risk of process break."
    else:
        psych_score = 86.0
        psych_why = f"Emotion tagged {emo} — steady enough to trade."
    dimensions.append(("psychology", psych_score, psych_why))

    # Execution
    eq = getattr(trade, "execution_quality", None)
    if eq is not None:
        try:
            stars = float(eq)
            exec_score = _clamp(stars / 5.0 * 100.0)
            exec_why = f"Execution quality logged at {stars:.0f}/5."
        except (TypeError, ValueError):
            exec_score = 65.0
            exec_why = "Execution quality present but unreadable."
    else:
        exec_score = 65.0
        exec_why = "No execution quality stars — neutral grade."
    dimensions.append(("execution", exec_score, exec_why))

    # Entry quality
    sq = getattr(trade, "setup_quality", None)
    if sq is not None:
        try:
            stars = float(sq)
            entry_score = _clamp(stars / 5.0 * 100.0)
            entry_why = f"Setup quality logged at {stars:.0f}/5."
        except (TypeError, ValueError):
            entry_score = 65.0
            entry_why = "Setup quality present but unreadable."
    else:
        conf = getattr(trade, "confidence_level", None)
        if conf is not None:
            try:
                entry_score = _clamp(float(conf) / 10.0 * 100.0)
                entry_why = f"Confidence {conf}/10 used as entry proxy."
            except (TypeError, ValueError):
                entry_score = 62.0
                entry_why = "Limited entry data — incomplete grade."
        else:
            entry_score = 62.0
            entry_why = "No setup quality — incomplete entry grade."
    dimensions.append(("entry", entry_score, entry_why))

    # Exit / patience (proxy from notes + R:R + discipline)
    notes = (
        (getattr(trade, "post_trade_notes", None) or "")
        + " "
        + (getattr(trade, "lessons_learned", None) or "")
    ).lower()
    exit_score = 68.0
    exit_why = "Exit quality inferred from available fields."
    if "early" in notes and ("close" in notes or "exit" in notes):
        exit_score = 48.0
        exit_why = "Notes suggest an early exit — review patience vs plan."
    elif "held" in notes or "target" in notes:
        exit_score = 82.0
        exit_why = "Notes suggest plan-aware exit management."
    disc = getattr(trade, "discipline_score", None)
    if disc is not None:
        try:
            exit_score = _clamp(0.5 * exit_score + 0.5 * (float(disc) / 10.0 * 100.0))
            exit_why += f" Discipline {disc}/10 factored in."
        except (TypeError, ValueError):
            pass
    dimensions.append(("exit", exit_score, exit_why))
    dimensions.append(("patience", exit_score, exit_why))

    grades = {
        key: {"letter": _letter(score), "score": round(score, 1), "why": why}
        for key, score, why in dimensions
    }
    overall = sum(s for _, s, _ in dimensions) / max(1, len(dimensions))
    return {
        "overall": {"letter": _letter(overall), "score": round(overall, 1)},
        "grades": grades,
        "trade_id": getattr(trade, "id", None),
        "symbol": getattr(trade, "symbol", None),
    }


def format_grades_text(payload: Dict[str, Any]) -> str:
    """Human-readable coach grade summary."""
    if not payload:
        return "Not enough fields to grade this trade yet."
    overall = payload.get("overall") or {}
    lines = [
        f"**Trade grade: {overall.get('letter', '—')}** "
        f"(score {overall.get('score', '—')})",
        "",
    ]
    labels = {
        "psychology": "Psychology",
        "execution": "Execution",
        "entry": "Entry",
        "exit": "Exit",
        "risk": "Risk",
        "patience": "Patience",
        "rules": "Rule adherence",
    }
    grades = payload.get("grades") or {}
    for key, label in labels.items():
        g = grades.get(key) or {}
        if not g:
            continue
        lines.append(f"- **{label}: {g.get('letter')}** — {g.get('why')}")
    lines.append("")
    lines.append("Next: tag emotion, confirm playbook, and always log SL before the next entry.")
    return "\n".join(lines)


def behaviour_forecast(user_id: int) -> str:
    """Evidence-only behaviour forecast (never market prediction)."""
    try:
        from app.models.trade import Trade

        trades = (
            Trade.query.filter(
                Trade.user_id == int(user_id),
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(30)
            .all()
        )
    except Exception:
        return ""
    if len(trades) < 5:
        return ""

    after_loss_risk = []
    after_win_risk = []
    for i in range(len(trades) - 1):
        prev = trades[i + 1]
        cur = trades[i]
        risk = getattr(cur, "risk_amount", None) or getattr(cur, "risk_percentage", None)
        if risk is None:
            continue
        try:
            rf = float(risk)
        except (TypeError, ValueError):
            continue
        prev_pnl = float(prev.profit_loss or 0)
        if prev_pnl < 0:
            after_loss_risk.append(rf)
        elif prev_pnl > 0:
            after_win_risk.append(rf)

    if len(after_loss_risk) >= 2 and len(after_win_risk) >= 2:
        avg_l = sum(after_loss_risk) / len(after_loss_risk)
        avg_w = sum(after_win_risk) / len(after_win_risk)
        if avg_w > 0 and avg_l > avg_w * 1.15:
            pct = ((avg_l / avg_w) - 1.0) * 100
            return (
                f"If you keep sizing up after losses, your journal shows risk after a loss runs "
                f"about {pct:.0f}% higher than after a win — historically that pairs with deeper drawdowns."
            )

    followed_wins = 0
    followed_n = 0
    broken_losses = 0
    broken_n = 0
    for t in trades:
        pnl = float(t.profit_loss or 0)
        if getattr(t, "playbook_followed", False):
            followed_n += 1
            if pnl > 0:
                followed_wins += 1
        else:
            broken_n += 1
            if pnl < 0:
                broken_losses += 1
    if followed_n >= 3 and broken_n >= 3:
        fw = followed_wins / followed_n * 100
        bl = broken_losses / broken_n * 100
        if fw >= bl + 10:
            return (
                f"Your journal indicates following the playbook wins about {fw:.0f}% of the time, "
                f"while off-plan trades lose about {bl:.0f}% of the time. Staying on-plan should improve consistency."
            )
    return ""
