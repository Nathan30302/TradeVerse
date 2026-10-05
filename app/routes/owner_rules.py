"""
Owner Rules Desk — multi-strategy bible, session gates, checklist, lot calc.
"""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services.owner_discipline import (
    advise_before_trade,
    build_desk_brief,
    calc_lot_size,
    calc_ten_two_two,
    get_active_strategy,
    get_or_create_rulebook,
    is_owner_discipline_user,
    list_strategies,
    record_day_trade_result,
    session_gate,
    set_active_strategy,
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


def _is_vincent(strategy) -> bool:
    return bool(strategy and (strategy.slug or "").startswith("vincent-desiano"))


def _desk_context(
    *,
    advice=None,
    advise_symbol="",
    advise_thesis="",
    lot_result=None,
    lot_form=None,
    risk_model_result=None,
    risk_model_form=None,
):
    book = get_or_create_rulebook(current_user)
    strategies = list_strategies(current_user)
    strategy = get_active_strategy(current_user, book)
    gate = session_gate(current_user, book, strategy)
    brief = build_desk_brief(current_user)
    return {
        "book": book,
        "strategies": strategies,
        "strategy": strategy,
        "gate": gate,
        "brief": brief,
        "risk": brief["risk"],
        "day": gate.get("day") or {},
        "checklist": brief.get("checklist") or {},
        "advice": advice,
        "advise_symbol": advise_symbol,
        "advise_thesis": advise_thesis,
        "lot_result": lot_result,
        "lot_form": lot_form or {},
        "risk_model_result": risk_model_result,
        "risk_model_form": risk_model_form or {},
        "is_vincent": _is_vincent(strategy),
    }


@bp.route("/")
@login_required
def desk():
    """Daily intelligence desk: strategy switcher, gate, checklist, lot calc."""
    _require_owner()
    return render_template("owner_rules/desk.html", **_desk_context())


@bp.route("/activate", methods=["POST"])
@login_required
def activate_strategy():
    _require_owner()
    try:
        sid = int(request.form.get("strategy_id") or 0)
    except (TypeError, ValueError):
        flash("Pick a valid strategy.", "danger")
        return redirect(url_for("owner_rules.desk"))
    s = set_active_strategy(current_user, sid)
    if not s:
        flash("Strategy not found.", "danger")
    else:
        flash(f"Active system: {s.name}", "success")
    return redirect(url_for("owner_rules.desk"))


@bp.route("/day-result", methods=["POST"])
@login_required
def day_result():
    _require_owner()
    result = (request.form.get("result") or "").strip().lower()
    if result not in ("win", "loss", "scratch"):
        flash("Log win, loss, or scratch.", "danger")
        return redirect(url_for("owner_rules.desk"))
    status = record_day_trade_result(current_user, result)
    if status.get("locked"):
        flash(status.get("reason") or "Day locked.", "warning")
    else:
        flash(
            f"Logged {result}. Trades today: {status['trades_today']}/{status['max_trades']}.",
            "success",
        )
    return redirect(url_for("owner_rules.desk"))


@bp.route("/lot-size", methods=["POST"])
@login_required
def lot_size():
    _require_owner()
    book = get_or_create_rulebook(current_user)
    strategy = get_active_strategy(current_user, book)
    risk = suggested_risk(book, strategy)
    form = {
        "balance": request.form.get("balance") or "",
        "risk_pct": request.form.get("risk_pct") or "",
        "sl_pips": request.form.get("sl_pips") or "",
        "pip_value": request.form.get("pip_value") or "10",
    }
    try:
        balance = float(form["balance"] or risk.get("balance") or 0)
        risk_pct = float(form["risk_pct"] or risk.get("risk_pct") or 1)
        sl_pips = float(form["sl_pips"] or 0)
        pip_value = float(form["pip_value"] or 10)
    except ValueError:
        flash("Check lot calculator numbers.", "danger")
        return redirect(url_for("owner_rules.desk"))
    result = calc_lot_size(balance=balance, risk_pct=risk_pct, sl_pips=sl_pips, pip_value=pip_value)
    return render_template(
        "owner_rules/desk.html",
        **_desk_context(lot_result=result, lot_form=form),
    )


@bp.route("/ten-two-two", methods=["POST"])
@login_required
def ten_two_two():
    """Vincent Desiano 10-2-2 position sizing calculator."""
    _require_owner()
    book = get_or_create_rulebook(current_user)
    strategy = get_active_strategy(current_user, book)
    risk = suggested_risk(book, strategy)
    form = {
        "balance": request.form.get("balance") or "",
        "allocation_pct": request.form.get("allocation_pct") or "10",
        "option_loss_pct": request.form.get("option_loss_pct") or "20",
    }
    try:
        balance = float(form["balance"] or risk.get("balance") or 0)
        allocation_pct = float(form["allocation_pct"] or 10)
        option_loss_pct = float(form["option_loss_pct"] or 20)
    except ValueError:
        flash("Check 10-2-2 calculator numbers.", "danger")
        return redirect(url_for("owner_rules.desk"))
    result = calc_ten_two_two(
        balance=balance,
        allocation_pct=allocation_pct,
        option_loss_pct=option_loss_pct,
    )
    return render_template(
        "owner_rules/desk.html",
        **_desk_context(risk_model_result=result, risk_model_form=form),
    )


@bp.route("/bible", methods=["GET", "POST"])
@login_required
def bible():
    """Strategy library + desk equity settings. Seeded systems are view-first."""
    _require_owner()
    book = get_or_create_rulebook(current_user)
    strategies = list_strategies(current_user)
    strategy = get_active_strategy(current_user, book)

    if request.method == "POST":
        action = (request.form.get("action") or "desk").strip()
        if action == "desk":
            book.gate_strict = request.form.get("gate_strict") == "on"
            book.enabled = request.form.get("enabled") == "on"
            try:
                book.risk_base_pct = float(request.form.get("risk_base_pct") or book.risk_base_pct or 1.0)
                book.risk_min_pct = float(request.form.get("risk_min_pct") or book.risk_min_pct or 0.25)
            except ValueError:
                flash("Check risk percentages.", "danger")
                return redirect(url_for("owner_rules.bible"))
            for field in (
                "account_starting_balance",
                "account_high_water",
                "account_current_balance",
            ):
                raw = (request.form.get(field) or "").strip()
                if raw == "":
                    continue
                try:
                    setattr(book, field, float(raw))
                except ValueError:
                    flash(f"Invalid number for {field}.", "danger")
                    return redirect(url_for("owner_rules.bible"))
            db.session.commit()
            flash("Desk equity & risk settings saved.", "success")
            return redirect(url_for("owner_rules.desk"))

        # Optional custom override on active strategy (notes / personal tweaks)
        if strategy and action == "strategy_notes":
            strategy.psychology_rules = (request.form.get("psychology_rules") or "").strip() or strategy.psychology_rules
            strategy.do_not_trade_rules = (
                request.form.get("do_not_trade_rules") or ""
            ).strip() or strategy.do_not_trade_rules
            raw_windows = (request.form.get("session_windows") or "").strip()
            if raw_windows:
                strategy.session_windows_json = windows_from_form(raw_windows)
                book.session_windows_json = strategy.session_windows_json
            db.session.commit()
            flash("Strategy notes updated.", "success")
            return redirect(url_for("owner_rules.bible"))

        flash("Nothing to save.", "info")
        return redirect(url_for("owner_rules.bible"))

    return render_template(
        "owner_rules/bible.html",
        book=book,
        strategies=strategies,
        strategy=strategy,
        windows_text=windows_as_text(strategy or book),
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
    strategy = get_active_strategy(current_user, book)
    advice = advise_before_trade(
        book,
        symbol=(request.form.get("symbol") or "").strip(),
        thesis=(request.form.get("thesis") or "").strip(),
        session_hint=(request.form.get("session_hint") or "").strip(),
        strategy=strategy,
    )
    return render_template(
        "owner_rules/desk.html",
        **_desk_context(
            advice=advice,
            advise_symbol=request.form.get("symbol") or "",
            advise_thesis=request.form.get("thesis") or "",
        ),
    )
