"""
Trade Planner Routes
Before/After trade planning workflow.

Lifecycle:
  PLANNING  --(start_execution)--> EXECUTED --(execute_plan POST)--> REVIEWED

Sync guarantee:
  - start_execution  creates a Trade (OPEN) and links it via executed_trade_id
  - execute_plan     closes that Trade (CLOSED + P&L) so dashboard picks it up
  - Both steps write to the SAME Trade model that My Trades and Dashboard read
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.trade_plan import TradePlan
from app.forms.trade_forms import TradePlanBeforeForm, TradePlanAfterForm
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
import os
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('planner', __name__, url_prefix='/planner')


# ==================== Internal helpers ====================

def _allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS', set())


def _save_screenshot(file, prefix='trade'):
    """Save an uploaded screenshot and return the relative static path, or None."""
    if not (file and file.filename and _allowed_file(file.filename)):
        return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = secure_filename(file.filename)
    unique_name = f"{prefix}_{current_user.id}_{timestamp}_{filename}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'trade_screenshots')
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, unique_name))
    return f"uploads/trade_screenshots/{unique_name}"


def _safe_float(value, default=None):
    """Convert value to float safely, returning default on failure."""
    try:
        return float(value) if value not in (None, '', 'None') else default
    except (TypeError, ValueError):
        return default


def _fallback_pnl(trade):
    """
    Calculate a simple directional P&L when the full calculator fails.
    Uses: (exit - entry) * lot_size * 100  for most instruments.
    This is intentionally simple — it guarantees a non-None value so the
    dashboard can count the trade. The full calculator is preferred.
    """
    try:
        entry = trade.entry_price or 0.0
        exit_ = trade.exit_price or 0.0
        lots  = trade.lot_size  or 1.0
        diff  = exit_ - entry if trade.trade_type == 'BUY' else entry - exit_
        return round(diff * lots * 100, 2)
    except Exception:
        return 0.0


def _close_trade_from_review(trade, actual_entry, actual_exit, plan_lot_size):
    """
    Close a linked Trade with reviewed prices and calculate P&L.
    Returns the final profit_loss value (always a number, never None).
    """
    from app.models.trade import Trade  # local to avoid circular import

    if actual_entry:
        trade.entry_price = actual_entry
    trade.exit_price = actual_exit
    trade.exit_date  = datetime.now(timezone.utc)
    trade.status     = 'CLOSED'

    # Try the full calculator first
    try:
        result = trade.calculate_pnl()
    except Exception as exc:
        logger.warning('calculate_pnl() raised for trade %s: %s', trade.id, exc)
        result = None

    # Fallback so profit_loss is never None going into the dashboard
    if result is None or trade.profit_loss is None:
        trade.profit_loss = _fallback_pnl(trade)
        logger.info(
            'Used fallback P&L %.2f for trade %s', trade.profit_loss, trade.id
        )

    return trade.profit_loss


# ==================== Trade Planner Dashboard ====================

@bp.route('/')
@login_required
def index():
    """List all trade plans with status filter and pagination."""
    status_filter = request.args.get('status', 'all')
    page          = request.args.get('page', 1, type=int)

    query = TradePlan.query.filter_by(user_id=current_user.id)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter.upper())
    query = query.order_by(TradePlan.created_at.desc())

    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    plans    = query.paginate(page=page, per_page=per_page, error_out=False)

    base_q         = TradePlan.query.filter_by(user_id=current_user.id)
    planning_count = base_q.filter_by(status='PLANNING').count()
    executed_count = base_q.filter_by(status='EXECUTED').count()
    reviewed_count = base_q.filter_by(status='REVIEWED').count()

    stats = {
        'total':    base_q.count(),
        'planning': planning_count,
        'executed': executed_count,
        'reviewed': reviewed_count,
    }

    return render_template('planner/index.html',
                           plans=plans,
                           status_filter=status_filter,
                           stats=stats)


# ==================== Step 1 — Create Plan ====================

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_plan():
    """Create a new trade plan (status = PLANNING). No Trade is created yet."""
    form = TradePlanBeforeForm()

    if form.validate_on_submit():
        try:
            plan = TradePlan(
                user_id=current_user.id,
                status='PLANNING',
                symbol=form.symbol.data.upper().strip(),
                direction=form.direction.data,
                planned_entry=form.planned_entry.data,
                planned_stop_loss=form.planned_stop_loss.data,
                planned_take_profit=form.planned_take_profit.data,
                planned_lot_size=form.planned_lot_size.data,
                strategy=form.strategy.data,
                market_structure_confirmed=form.market_structure_confirmed.data,
                liquidity_taken=form.liquidity_taken.data,
                confirmation_candle_formed=form.confirmation_candle_formed.data,
                session_aligned=form.session_aligned.data,
                pre_trade_notes=form.pre_trade_notes.data,
            )
            plan.calculate_planned_rr()

            if form.screenshot_before.data:
                path = _save_screenshot(form.screenshot_before.data, 'before')
                if path:
                    plan.screenshot_before_path = path

            plan.calculate_plan_quality()
            db.session.add(plan)
            db.session.commit()

            rr = plan.planned_rr_ratio or 0
            flash(f'✅ Trade plan created! Planned R:R = 1:{rr:.2f}', 'success')
            return redirect(url_for('planner.view_plan', plan_id=plan.id))

        except Exception as exc:
            db.session.rollback()
            logger.exception('Error creating plan')
            flash(f'❌ Error creating plan: {exc}', 'danger')

    return render_template('planner/new_plan.html', form=form)


# ==================== View Plan ====================

@bp.route('/<int:plan_id>')
@login_required
def view_plan(plan_id):
    """View a trade plan. Passive sync keeps status consistent with Trade."""
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    try:
        if plan.sync_with_trade():
            db.session.commit()
    except Exception:
        db.session.rollback()

    return render_template('planner/view_plan.html', plan=plan)


# ==================== Step 2 — Execute Plan (create Trade) ====================

@bp.route('/<int:plan_id>/start', methods=['POST'])
@login_required
def start_execution(plan_id):
    """
    Step 2: mark plan EXECUTED and create the linked Trade (status=OPEN).

    The Trade goes into My Trades immediately. Dashboard will count it in
    OPEN stats. Closing happens in execute_plan (Step 3).
    """
    from app.models.trade import Trade

    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    # Guard: already past PLANNING
    if plan.status in ('EXECUTED', 'REVIEWED'):
        existing_id = plan.executed_trade_id or getattr(plan, 'trade_id', None)
        flash('This plan has already been executed.', 'info')
        if existing_id:
            return redirect(url_for('trade.view', trade_id=existing_id))
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    try:
        trade_type  = (request.form.get('trade_type') or plan.direction or 'BUY').upper()
        entry_price = _safe_float(request.form.get('entry_price'), plan.planned_entry  or 0.0)
        stop_loss   = _safe_float(request.form.get('stop_loss'),   plan.planned_stop_loss)
        take_profit = _safe_float(request.form.get('take_profit'), plan.planned_take_profit)
        lot_size    = _safe_float(request.form.get('lot_size'),    plan.planned_lot_size or 1.0)
        strategy    = request.form.get('strategy') or plan.strategy or ''
        notes       = request.form.get('pre_trade_plan') or plan.pre_trade_notes or ''

        trade = Trade(
            user_id=current_user.id,
            symbol=plan.symbol.upper(),
            trade_type=trade_type,
            lot_size=lot_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_date=datetime.now(timezone.utc),
            pre_trade_plan=notes,
            strategy=strategy,
            status='OPEN',
            # Populate extra fields so dashboard analytics are richer
            checklist_completed=bool(plan.get_checklist_score() == 4),
            playbook_followed=True,
        )

        # Calculate R:R on the Trade if levels are available
        if trade.stop_loss and trade.take_profit and trade.entry_price:
            try:
                trade.calculate_risk_reward()
            except Exception:
                pass

        db.session.add(trade)
        db.session.flush()  # assign trade.id before linking

        # Link plan → trade (both FK columns for compatibility)
        plan.executed_trade_id = trade.id
        try:
            plan.trade_id = trade.id   # unique FK — may raise if already set
        except Exception:
            pass
        plan.executed = True
        plan.mark_as_executed()        # status='EXECUTED', executed_at=now

        db.session.commit()

        flash(
            '✅ Trade created and marked as Executed. '
            'It now appears in My Trades (status: OPEN). '
            'Complete the review when you close it.',
            'success'
        )
        return redirect(url_for('trade.view', trade_id=trade.id))

    except Exception as exc:
        db.session.rollback()
        logger.exception('Error in start_execution for plan %s', plan_id)
        flash(f'❌ Error executing plan: {exc}', 'danger')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))


# ==================== Step 3 — Review Trade ====================

@bp.route('/<int:plan_id>/execute', methods=['GET', 'POST'])
@login_required
def execute_plan(plan_id):
    """
    Step 3: post-trade review form.

    On submit:
      1. Saves review fields (grade, emotion, reflection) on the plan
      2. Closes the linked Trade with actual exit price + calculated P&L
      3. Marks plan REVIEWED
      4. Dashboard + My Trades automatically reflect the closed Trade

    Status guards:
      PLANNING  → redirected to view (must execute first)
      REVIEWED  → redirected to view (already done)
      EXECUTED  → proceeds normally
    """
    from app.models.trade import Trade

    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    if plan.status == 'REVIEWED':
        flash('This trade has already been reviewed.', 'info')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    if plan.status == 'PLANNING':
        flash('You must execute the plan first before reviewing it.', 'warning')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    # status == 'EXECUTED' — proceed to review form
    form = TradePlanAfterForm()

    if request.method == 'GET':
        # Pre-fill actual_entry from the linked Trade if available
        linked = None
        if plan.executed_trade_id:
            linked = db.session.get(Trade, plan.executed_trade_id)
        form.actual_entry.data = (
            (linked.entry_price if linked else None)
            or plan.planned_entry
        )

    if form.validate_on_submit():
        try:
            actual_entry = form.actual_entry.data
            actual_exit  = form.actual_exit.data

            # --- Update plan review fields ---
            plan.actual_entry     = actual_entry
            plan.actual_exit      = actual_exit
            plan.emotion_after    = form.emotion_after.data
            plan.trade_grade      = form.trade_grade.data
            plan.reflection_notes = form.reflection_notes.data

            # --- Close the linked Trade ---
            # Accept any non-CANCELLED status so manual edits via My Trades
            # don't block the review from syncing.
            final_pnl = None
            if plan.executed_trade_id and actual_exit:
                trade = db.session.get(Trade, plan.executed_trade_id)
                if trade and trade.status != 'CANCELLED':
                    final_pnl = _close_trade_from_review(
                        trade, actual_entry, actual_exit, plan.planned_lot_size
                    )
                    plan.actual_pnl = final_pnl
                    logger.info(
                        'Plan %s review: closed Trade %s, P/L=%.2f',
                        plan.id, trade.id, final_pnl or 0
                    )
            elif actual_exit:
                # Plan was reviewed without a linked Trade — store P&L on plan only
                # (trade was never created via start_execution)
                pass

            # --- Screenshot ---
            if form.screenshot_after.data:
                path = _save_screenshot(form.screenshot_after.data, 'after')
                if path:
                    plan.screenshot_after_path = path

            # --- Finalise plan ---
            plan.mark_as_reviewed()
            plan.calculate_execution_quality()

            db.session.commit()

            pnl_str = f"${final_pnl:+.2f}" if final_pnl is not None else "N/A"
            flash(
                f'✅ Trade reviewed! P&L: {pnl_str}. '
                'Dashboard and My Trades have been updated.',
                'success'
            )
            return redirect(url_for('planner.view_plan', plan_id=plan.id))

        except Exception as exc:
            db.session.rollback()
            logger.exception('Error in execute_plan for plan %s', plan_id)
            flash(f'❌ Error saving review: {exc}', 'danger')

    return render_template('planner/execute_plan.html', form=form, plan=plan)


# ==================== Edit Plan ====================

@bp.route('/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    """Edit a PLANNING plan. Locked after execution."""
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    if plan.status != 'PLANNING':
        flash('Only unexecuted plans can be edited.', 'warning')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    form = TradePlanBeforeForm(obj=plan)

    if form.validate_on_submit():
        try:
            plan.symbol                     = form.symbol.data.upper().strip()
            plan.direction                  = form.direction.data
            plan.planned_entry              = form.planned_entry.data
            plan.planned_stop_loss          = form.planned_stop_loss.data
            plan.planned_take_profit        = form.planned_take_profit.data
            plan.planned_lot_size           = form.planned_lot_size.data
            plan.strategy                   = form.strategy.data
            plan.market_structure_confirmed = form.market_structure_confirmed.data
            plan.liquidity_taken            = form.liquidity_taken.data
            plan.confirmation_candle_formed = form.confirmation_candle_formed.data
            plan.session_aligned            = form.session_aligned.data
            plan.pre_trade_notes            = form.pre_trade_notes.data

            plan.calculate_planned_rr()
            plan.calculate_plan_quality()

            if form.screenshot_before.data:
                path = _save_screenshot(form.screenshot_before.data, 'before')
                if path:
                    plan.screenshot_before_path = path

            db.session.commit()
            flash('✅ Trade plan updated!', 'success')
            return redirect(url_for('planner.view_plan', plan_id=plan.id))

        except Exception as exc:
            db.session.rollback()
            flash(f'❌ Error: {exc}', 'danger')

    return render_template('planner/edit_plan.html', form=form, plan=plan)


# ==================== Delete Plan ====================

@bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_plan(plan_id):
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(plan)
        db.session.commit()
        flash('✅ Trade plan deleted.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'❌ Error: {exc}', 'danger')
    return redirect(url_for('planner.index'))


# ==================== Legacy routes (backward compatibility) ====================

@bp.route('/create/<int:trade_id>', methods=['GET', 'POST'])
@login_required
def create_plan(trade_id):
    flash('Trade planning has been redesigned. Use the new Trade Planner.', 'info')
    return redirect(url_for('planner.new_plan'))


@bp.route('/view/<int:trade_id>')
@login_required
def view_plan_legacy(trade_id):
    from app.models.trade import Trade
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    if trade.has_plan():
        plan = trade.get_plan()
        if plan:
            return redirect(url_for('planner.view_plan', plan_id=plan.id))
    flash('No plan found for this trade.', 'warning')
    return redirect(url_for('planner.new_plan'))


@bp.route('/review/<int:trade_id>', methods=['GET', 'POST'])
@login_required
def review_trade(trade_id):
    from app.models.trade import Trade
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    if trade.has_plan():
        plan = trade.get_plan()
        if plan:
            return redirect(url_for('planner.execute_plan', plan_id=plan.id))
    flash('No plan found for this trade.', 'warning')
    return redirect(url_for('planner.new_plan'))


# ==================== API: P&L Calculator ====================

@bp.route('/api/calculate-pnl', methods=['POST'])
@login_required
def api_calculate_pnl():
    from app.utils.pnl_calculator import calculate_pnl
    try:
        data        = request.get_json() or {}
        symbol      = data.get('symbol', '').upper().strip()
        trade_type  = data.get('trade_type', 'BUY').upper()
        entry_price = _safe_float(data.get('entry_price'), 0.0)
        exit_price  = _safe_float(data.get('exit_price'),  0.0)
        lot_size    = _safe_float(data.get('lot_size'),    0.01)

        if not all([symbol, entry_price, exit_price, lot_size]):
            return jsonify({'error': 'Missing required fields'}), 400

        pnl, pips, asset_desc = calculate_pnl(
            symbol=symbol,
            trade_type=trade_type,
            entry_price=entry_price,
            exit_price=exit_price,
            lot_size=lot_size,
        )
        return jsonify({
            'success':    True,
            'pnl':        round(pnl, 2),
            'pips':       round(pips, 1),
            'asset_type': asset_desc,
        })

    except Exception as exc:
        return jsonify({'error': str(exc)}), 400