"""
Owner Rules Desk — Nathan-only strategy bible, time gates, risk coach.
"""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services.owner_discipline import (
    advise_before_trade,
    build_multi_tf_brief,
    get_or_create_rulebook,
    is_owner_discipline_user,
    session_gate,
    suggested_risk,
    unlock_session_today,
    update_balance,
    windows_as_text,
    windows_from_form,
)

bp = Blueprint("owner_rules", __name__, url_prefix="/owner/rules")


def _require_owner():
    if not is_owner_discipline_user(current_user):
        abort(404)  # hide existence from non-owners


@bp.route("/")
@login_required
def desk():
    """Daily intelligence desk: gate, risk, multi-TF brief."""
    _require_owner()
    book = get_or_create_rulebook(current_user)
    gate = session_gate(current_user, book)
    brief = build_multi_tf_brief(book, gate)
    return render_template(
        "owner_rules/desk.html",
        book=book,
        gate=gate,
        brief=brief,
        risk=brief["risk"],
    )


@bp.route("/bible", methods=["GET", "POST"])
@login_required
def bible():
    """Write / edit the full trading system in detail."""
    _require_owner()
    book = get_or_create_rulebook(current_user)
    if request.method == "POST":
        book.strategy_name = (request.form.get("strategy_name") or "My system").strip()[:160]
        book.overview = (request.form.get("overview") or "").strip() or None
        book.markets = (request.form.get("markets") or "").strip() or None
        book.timeframes = (request.form.get("timeframes") or "").strip()[:120] or None
        book.weekly_bias_rules = (request.form.get("weekly_bias_rules") or "").strip() or None
        book.daily_bias_rules = (request.form.get("daily_bias_rules") or "").strip() or None
        book.h4_rules = (request.form.get("h4_rules") or "").strip() or None
        book.m15_rules = (request.form.get("m15_rules") or "").strip() or None
        book.entry_rules = (request.form.get("entry_rules") or "").strip() or None
        book.exit_rules = (request.form.get("exit_rules") or "").strip() or None
        book.invalidation_rules = (request.form.get("invalidation_rules") or "").strip() or None
        book.do_not_trade_rules = (request.form.get("do_not_trade_rules") or "").strip() or None
        book.psychology_rules = (request.form.get("psychology_rules") or "").strip() or None
        book.session_windows_json = windows_from_form(request.form.get("session_windows") or "")
        book.gate_strict = request.form.get("gate_strict") == "on"
        book.enabled = request.form.get("enabled") == "on"
        try:
            book.risk_base_pct = float(request.form.get("risk_base_pct") or 1.0)
            book.risk_min_pct = float(request.form.get("risk_min_pct") or 0.25)
        except ValueError:
            flash("Check risk percentages.", "danger")
            return redirect(url_for("owner_rules.bible"))
        for field, key in (
            ("account_starting_balance", "account_starting_balance"),
            ("account_high_water", "account_high_water"),
            ("account_current_balance", "account_current_balance"),
        ):
            raw = (request.form.get(field) or "").strip()
            if raw == "":
                continue
            try:
                setattr(book, key, float(raw))
            except ValueError:
                flash(f"Invalid number for {field}.", "danger")
                return redirect(url_for("owner_rules.bible"))
        mt = (request.form.get("max_trades_per_day") or "").strip()
        ml = (request.form.get("max_losses_in_row") or "").strip()
        book.max_trades_per_day = int(mt) if mt.isdigit() else None
        book.max_losses_in_row = int(ml) if ml.isdigit() else None
        db.session.commit()
        flash("Your trading bible is saved. The desk will coach from these rules only.", "success")
        return redirect(url_for("owner_rules.desk"))

    return render_template(
        "owner_rules/bible.html",
        book=book,
        windows_text=windows_as_text(book),
    )


@bp.route("/unlock", methods=["POST"])
@login_required
def unlock():
    _require_owner()
    book = get_or_create_rulebook(current_user)
    note = (request.form.get("note") or "").strip()
    unlock_session_today(current_user, book, note=note)
    flash("Today’s session is unlocked. Still follow your written rules — this is not a free pass.", "warning")
    return redirect(url_for("owner_rules.desk"))


@bp.route("/balance", methods=["POST"])
@login_required
def balance():
    _require_owner()
    book = get_or_create_rulebook(current_user)
    try:
        current = float(request.form.get("account_current_balance") or 0)
    except ValueError:
        flash("Enter a valid balance.", "danger")
        return redirect(url_for("owner_rules.desk"))
    risk = update_balance(book, current, bump_high_water=True)
    flash(
        f"Balance updated. Suggested risk now {risk['risk_pct']}% ({risk['mode']} mode).",
        "success",
    )
    return redirect(url_for("owner_rules.desk"))


@bp.route("/advise", methods=["POST"])
@login_required
def advise():
    _require_owner()
    book = get_or_create_rulebook(current_user)
    advice = advise_before_trade(
        book,
        symbol=(request.form.get("symbol") or "").strip(),
        thesis=(request.form.get("thesis") or "").strip(),
        session_hint=(request.form.get("session_hint") or "").strip(),
    )
    gate = session_gate(current_user, book)
    brief = build_multi_tf_brief(book, gate)
    return render_template(
        "owner_rules/desk.html",
        book=book,
        gate=gate,
        brief=brief,
        risk=brief["risk"],
        advice=advice,
        advise_symbol=request.form.get("symbol") or "",
        advise_thesis=request.form.get("thesis") or "",
    )
