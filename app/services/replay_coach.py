"""
Trade Replay coach walkthrough — narrative from journal + replay events.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_replay_walkthrough(user, trade, events: List[Any] | None = None) -> Dict[str, Any]:
    """
    Walk through entry → manage → exit with coach grades and lessons.
    Evidence-only; no market predictions.
    """
    from app.services.trade_coach_grades import grade_trade, format_grades_text

    events = events or []
    grades = grade_trade(trade)
    pnl = float(getattr(trade, "profit_loss", None) or 0)
    sym = getattr(trade, "symbol", None) or "trade"
    emo = (getattr(trade, "emotion", None) or "").strip()
    plan = (getattr(trade, "pre_trade_plan", None) or "").strip()
    notes = (getattr(trade, "post_trade_notes", None) or getattr(trade, "lessons_learned", None) or "").strip()
    followed = bool(getattr(trade, "playbook_followed", False))
    has_sl = getattr(trade, "stop_loss", None) is not None

    sections: List[Dict[str, str]] = []

    # Entry
    entry_bits = []
    if plan:
        entry_bits.append(f"Plan: {plan[:220]}")
    else:
        entry_bits.append("No pre-trade plan logged — entry reasoning is incomplete.")
    if has_sl:
        entry_bits.append("Stop was defined.")
    else:
        entry_bits.append("No stop logged — undefined risk.")
    g_entry = (grades.get("grades") or {}).get("entry") or {}
    if g_entry:
        entry_bits.append(f"Entry grade {g_entry.get('letter')}: {g_entry.get('why')}")
    sections.append({"title": "Entry reasoning", "body": " ".join(entry_bits)})

    # Manage / events
    manage_notes = []
    for ev in events:
        et = (getattr(ev, "event_type", None) or "").lower()
        note = (getattr(ev, "note", None) or "").strip()
        if et in ("manage", "entry", "before") and note:
            manage_notes.append(f"{et}: {note[:160]}")
    if manage_notes:
        sections.append(
            {
                "title": "Management",
                "body": "Replay trail — " + " · ".join(manage_notes[:5]),
            }
        )
    else:
        sections.append(
            {
                "title": "Management",
                "body": "No manage events on the replay timeline yet. Add before/entry/manage notes while you review.",
            }
        )

    # Exit
    exit_bits = []
    if pnl > 0:
        exit_bits.append(f"Winner on {sym} ({pnl:+.2f}).")
    elif pnl < 0:
        exit_bits.append(f"Loss on {sym} ({pnl:+.2f}).")
    else:
        exit_bits.append(f"Flat close on {sym}.")
    if followed:
        exit_bits.append("Playbook marked followed.")
    else:
        exit_bits.append("Playbook not marked followed.")
    g_exit = (grades.get("grades") or {}).get("exit") or {}
    if g_exit:
        exit_bits.append(f"Exit grade {g_exit.get('letter')}: {g_exit.get('why')}")
    sections.append({"title": "Exit reasoning", "body": " ".join(exit_bits)})

    # Psychology
    psych = (grades.get("grades") or {}).get("psychology") or {}
    sections.append(
        {
            "title": "Psychology",
            "body": (f"Emotion: {emo}. " if emo else "No emotion tagged. ")
            + (psych.get("why") or ""),
        }
    )

    # Mistakes / strengths
    strengths = []
    mistakes = []
    if has_sl:
        strengths.append("Risk was defined with a stop.")
    else:
        mistakes.append("Undefined risk (no SL).")
    if followed:
        strengths.append("Stayed on playbook.")
    elif pnl < 0:
        mistakes.append("Off-playbook on a loser.")
    if notes:
        strengths.append("Left a post-trade note — good for pattern finding.")
    else:
        mistakes.append("Missing post-trade lesson.")

    sections.append(
        {
            "title": "What worked",
            "body": " ".join(strengths) if strengths else "Not enough process marks to celebrate yet.",
        }
    )
    sections.append(
        {
            "title": "What to tighten",
            "body": " ".join(mistakes) if mistakes else "Process looks solid on the fields we have.",
        }
    )

    alt = (
        "Alternative: only take this setup when checklist + SL + planned R:R ≥ 1.5 are complete "
        "before entry — skip if emotion is revenge/FOMO."
    )
    sections.append({"title": "Alternative action", "body": alt})
    sections.append(
        {
            "title": "Lesson",
            "body": notes[:280] if notes else "Write one honest line now so this replay teaches you next week.",
        }
    )

    narrative = "\n\n".join(f"**{s['title']}**\n{s['body']}" for s in sections)
    overall = grades.get("overall") or {}
    return {
        "symbol": sym,
        "overall_grade": overall.get("letter"),
        "overall_score": overall.get("score"),
        "grades_text": format_grades_text(grades),
        "sections": sections,
        "narrative": narrative,
        "next_step": "Save one rule from this replay as your weekly focus, then take the next 5 trades under it.",
    }
