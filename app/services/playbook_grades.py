"""
Playbook setup grades — how traders classify edge before / after journaling experience.

Beginners explore many setups to learn what the market gives them.
Experienced traders focus on a few high-grade setups (Pareto / 80–20).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# (code, default typical R:R, short coach note)
SETUP_GRADE_OPTIONS: List[Tuple[str, float, str]] = [
    ("A++", 4.0, "Rare A++ — often ~1:4+. Wait for it; don’t force size on lesser setups."),
    ("A+", 3.0, "Strong A+ — often reaches ~1:3. Core focus setup for experienced traders."),
    ("A-", 2.5, "Solid A− — often ~1:2.5. Still high quality; keep in your focus list."),
    ("B+", 2.0, "B+ — often ~1:2. Acceptable focus when A setups are quiet."),
    ("B-", 1.8, "B− — often ~1:1.8. Journal it; size down vs your A grades."),
    ("C", 1.5, "C — learning / lower edge. Great for experience; not for max size."),
]

SETUP_GRADE_CODES = {g[0] for g in SETUP_GRADE_OPTIONS}
FOCUS_GRADES = {"A++", "A+", "A-", "B+"}
_DEFAULT_RR = {code: rr for code, rr, _ in SETUP_GRADE_OPTIONS}
_NOTES = {code: note for code, _, note in SETUP_GRADE_OPTIONS}


def normalize_setup_grade(raw: Optional[str]) -> str:
    """Return a known grade code or empty string."""
    g = (raw or "").strip().upper().replace(" ", "")
    # Normalize unicode minus / en-dash to ASCII hyphen
    g = g.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    # Allow a / a+ style typos
    aliases = {
        "A++": "A++",
        "A+": "A+",
        "A": "A-",
        "A-": "A-",
        "B++": "B+",
        "B+": "B+",
        "B": "B-",
        "B-": "B-",
        "C": "C",
        "C+": "C",
    }
    return aliases.get(g, g if g in SETUP_GRADE_CODES else "")


def default_typical_rr(grade: str) -> Optional[float]:
    g = normalize_setup_grade(grade)
    return _DEFAULT_RR.get(g)


def grade_coach_note(grade: str) -> str:
    g = normalize_setup_grade(grade)
    return _NOTES.get(g, "")


def is_focus_grade(grade: str) -> bool:
    return normalize_setup_grade(grade) in FOCUS_GRADES


def parse_typical_rr(raw: Optional[str], *, grade: str = "") -> Optional[float]:
    """Parse user typical R:R; fall back to grade default when blank."""
    text = (raw or "").strip().replace(",", ".")
    if text:
        try:
            val = float(text)
            if val <= 0 or val > 50:
                return None
            return round(val, 2)
        except (TypeError, ValueError):
            return None
    return default_typical_rr(grade)


def focus_summary(setups: List[Any]) -> Dict[str, Any]:
    """Build 80/20 focus advice from a user's setups."""
    graded = []
    for s in setups or []:
        g = normalize_setup_grade(getattr(s, "setup_grade", None) or "")
        if not g:
            continue
        graded.append(
            {
                "id": getattr(s, "id", None),
                "name": getattr(s, "name", "") or "Setup",
                "grade": g,
                "typical_rr": getattr(s, "typical_rr", None) or default_typical_rr(g),
                "is_focus": g in FOCUS_GRADES,
                "is_active": bool(getattr(s, "is_active", True)),
            }
        )

    focus = [x for x in graded if x["is_focus"] and x["is_active"]]
    focus.sort(key=lambda x: (["A++", "A+", "A-", "B+"].index(x["grade"]), -(x["typical_rr"] or 0)))
    other = [x for x in graded if not x["is_focus"]]

    return {
        "graded_count": len(graded),
        "focus": focus[:5],
        "other_count": len(other),
        "ungraded_count": max(0, len(setups or []) - len(graded)),
        "message": (
            "After you have real data, put most of your attention (and size) on "
            "A++ / A+ / A− / B+ setups — the ~20% of patterns that often drive ~80% of profits. "
            "They won’t appear every day; wait for them."
            if focus
            else (
                "Grade each playbook (A++ → C) by the R:R it usually delivers. "
                "As you gain experience, focus on 2–3 high grades instead of chasing every setup."
            )
        ),
    }


# Minimum linked closed trades before we suggest a setup grade from data.
SUGGEST_MIN_TRADES = 5

# Midpoints / floors for mapping realized avg R:R → setup grade (highest first).
_SUGGEST_RR_BANDS: List[Tuple[str, float]] = [
    ("A++", 3.6),
    ("A+", 2.75),
    ("A-", 2.25),
    ("B+", 1.9),
    ("B-", 1.65),
    ("C", 0.0),
]


def suggest_grade_from_trades(
    avg_rr: float,
    *,
    win_rate: float = 0.0,
    count: int = 0,
    current_grade: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Suggest a setup grade (A++–C) from realized avg R:R after enough linked trades.

    Separate from Results letter grade (A–D quality). Returns None until
    ``SUGGEST_MIN_TRADES`` linked trades exist.
    """
    if int(count or 0) < SUGGEST_MIN_TRADES:
        return None
    try:
        rr = float(avg_rr or 0.0)
    except (TypeError, ValueError):
        rr = 0.0
    if rr <= 0:
        return None

    code = "C"
    for grade, floor in _SUGGEST_RR_BANDS:
        if rr >= floor:
            code = grade
            break

    # Soft downgrade when win rate is weak — edge may not justify the R:R label.
    try:
        wr = float(win_rate or 0.0)
    except (TypeError, ValueError):
        wr = 0.0
    order = ["A++", "A+", "A-", "B+", "B-", "C"]
    if wr < 40 and code in order:
        idx = min(len(order) - 1, order.index(code) + 1)
        code = order[idx]
    elif wr < 50 and code in ("A++", "A+"):
        code = "A-" if code == "A+" else "A+"

    typical = default_typical_rr(code) or round(rr, 2)
    current = normalize_setup_grade(current_grade)
    return {
        "grade": code,
        "typical_rr": typical,
        "avg_rr": round(rr, 2),
        "count": int(count),
        "win_rate": round(wr, 1),
        "differs_from_current": (not current) or (current != code),
        "message": (
            f"From {int(count)} linked trades (avg R:R ~1:{rr:.1f}"
            + (f", {wr:.0f}% WR" if wr else "")
            + f"), this setup looks like {code} (~1:{typical:g})."
        ),
    }
