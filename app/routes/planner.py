"""
Trade Planner Routes
Redesigned for standalone Before/After trade planning workflow
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.trade_plan import TradePlan
from app.forms.trade_forms import TradePlanBeforeForm, TradePlanAfterForm
from werkzeug.utils import secure_filename
from datetime import datetime
import os

bp = Blueprint('planner', __name__, url_prefix='/planner')


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_screenshot(file, prefix='trade'):
    """Save uploaded screenshot and return path"""
    if file and file.filename and allowed_file(file.filename):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        unique_filename = f"{prefix}_{current_user.id}_{timestamp}_{filename}"
        
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'trade_screenshots')
        os.makedirs(upload_dir, exist_ok=True)
        
        filepath = os.path.join(upload_dir, unique_filename)
        file.save(filepath)
        
        return f"uploads/trade_screenshots/{unique_filename}"
    
    return None


# ==================== Trade Planner Dashboard ====================

@bp.route('/')
@login_required
def index():
    """
    Trade Planner Dashboard
    Shows all trade plans with their statuses
    """
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    
    query = TradePlan.query.filter_by(user_id=current_user.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter.upper())
    
    query = query.order_by(TradePlan.created_at.desc())
    
    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    plans = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get stats
    total_plans = TradePlan.query.filter_by(user_id=current_user.id).count()
    planning_count = TradePlan.query.filter_by(user_id=current_user.id, status='PLANNING').count()
    executed_count = TradePlan.query.filter_by(user_id=current_user.id, status='EXECUTED').count()
    reviewed_count = TradePlan.query.filter_by(user_id=current_user.id, status='REVIEWED').count()
    
    stats = {
        'total': total_plans,
        'planning': planning_count,
        'executed': executed_count,
        'reviewed': reviewed_count
    }
    
    return render_template('planner/index.html', 
                         plans=plans, 
                         status_filter=status_filter,
                         stats=stats)


# ==================== Create New Trade Plan ====================

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_plan():
    """
    Create a new trade plan (Before Trade section)
    """
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
                pre_trade_notes=form.pre_trade_notes.data
            )
            
            # Calculate planned R:R
            plan.calculate_planned_rr()
            
            # Handle screenshot upload
            if form.screenshot_before.data:
                screenshot_path = save_screenshot(form.screenshot_before.data, 'before')
                if screenshot_path:
                    plan.screenshot_before_path = screenshot_path
            
            # Calculate plan quality
            plan.calculate_plan_quality()
            
            db.session.add(plan)
            db.session.commit()
            
            flash(f'✅ Trade plan created! R:R = 1:{plan.planned_rr_ratio or 0:.2f}', 'success')
            return redirect(url_for('planner.view_plan', plan_id=plan.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error creating plan: {str(e)}', 'danger')
            print(f"Error: {e}")
    
    return render_template('planner/new_plan.html', form=form)


# ==================== View Trade Plan ====================

@bp.route('/<int:plan_id>')
@login_required
def view_plan(plan_id):
    """View trade plan details"""
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    
    return render_template('planner/view_plan.html', plan=plan)


# ==================== Execute Trade (Mark as Executed) ====================

@bp.route('/<int:plan_id>/execute', methods=['GET', 'POST'])
@login_required
def execute_plan(plan_id):
    """
    Mark plan as executed and enter actual entry/exit details
    """
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    
    if plan.status == 'REVIEWED':
        flash('This trade has already been reviewed.', 'info')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))
    
    form = TradePlanAfterForm()
    
    # Pre-fill with planned values if not submitted
    if request.method == 'GET':
        form.actual_entry.data = plan.planned_entry
    
    if form.validate_on_submit():
        try:
            plan.actual_entry = form.actual_entry.data
            plan.actual_exit = form.actual_exit.data
            plan.emotion_after = form.emotion_after.data
            plan.trade_grade = form.trade_grade.data
            plan.reflection_notes = form.reflection_notes.data
            
            # Calculate P&L using the universal calculator
            plan.calculate_pnl()
            
            # Handle screenshot upload
            if form.screenshot_after.data:
                screenshot_path = save_screenshot(form.screenshot_after.data, 'after')
                if screenshot_path:
                    plan.screenshot_after_path = screenshot_path
            
            # Mark as reviewed
            plan.mark_as_reviewed()
            plan.calculate_execution_quality()
            
            db.session.commit()
            
            pnl_display = f"${plan.actual_pnl:+.2f}" if plan.actual_pnl else "N/A"
            flash(f'✅ Trade review completed! P&L: {pnl_display}', 'success')
            return redirect(url_for('planner.view_plan', plan_id=plan.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error: {str(e)}', 'danger')
            print(f"Error: {e}")
    
    return render_template('planner/execute_plan.html', form=form, plan=plan)


@bp.route('/<int:plan_id>/start', methods=['POST'])
@login_required
def start_execution(plan_id):
    """
    Start execution: create a Trade record from a TradePlan and link them.
    This prevents duplicate manual entry — clicking Execute will create the trade
    and transition the plan to EXECUTED. Redirects to the trade view for further actions.
    """
    from app.models.trade import Trade

    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    # If already linked to a trade, redirect to that trade
    if getattr(plan, 'executed', False) or getattr(plan, 'executed_trade_id', None) or getattr(plan, 'trade_id', None):
        existing_id = getattr(plan, 'executed_trade_id', None) or getattr(plan, 'trade_id', None)
        flash('This plan has already been executed and linked to a trade.', 'info')
        if existing_id:
            return redirect(url_for('trade.view', trade_id=existing_id))
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    if plan.status == 'REVIEWED':
        flash('This plan has already been reviewed.', 'info')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))

    try:
        # Allow overriding planned values from an inline modal form
        trade_type = (request.form.get('trade_type') or plan.direction or 'BUY').upper()
        # parse numeric fields safely
        def to_float(val, default=None):
            try:
                return float(val) if val is not None and val != '' else default
            except Exception:
                return default

        entry_price = to_float(request.form.get('entry_price'), plan.planned_entry or 0.0)
        stop_loss = to_float(request.form.get('stop_loss'), plan.planned_stop_loss)
        take_profit = to_float(request.form.get('take_profit'), plan.planned_take_profit)
        lot_size = to_float(request.form.get('lot_size'), plan.planned_lot_size or 1.0)
        strategy = request.form.get('strategy') or plan.strategy
        pre_trade_plan = request.form.get('pre_trade_plan') or plan.pre_trade_notes or ''

        # Create trade using planned or overridden values
        trade = Trade(
            user_id=current_user.id,
            symbol=(plan.symbol or '').upper(),
            trade_type=trade_type,
            lot_size=lot_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_date=plan.executed_at or datetime.utcnow(),
            pre_trade_plan=pre_trade_plan,
            strategy=strategy
        )

        db.session.add(trade)
        db.session.flush()  # get trade.id

        # Link plan -> trade and mark executed
        # Support both legacy `trade_id` and new `executed` fields
        try:
            plan.trade_id = trade.id
        except Exception:
            pass
        plan.executed = True
        plan.executed_trade_id = trade.id
        plan.mark_as_executed()

        db.session.commit()

        flash('Plan executed: trade created under My Trades.', 'success')
        return redirect(url_for('trade.view', trade_id=trade.id))

    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error executing plan: {str(e)}', 'danger')
        current_app.logger.exception('Error starting execution for plan %s', plan_id)
        return redirect(url_for('planner.view_plan', plan_id=plan.id))


# ==================== Edit Trade Plan ====================

@bp.route('/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    """Edit existing trade plan (before section only)"""
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    
    if plan.status == 'REVIEWED':
        flash('Cannot edit a reviewed trade plan.', 'warning')
        return redirect(url_for('planner.view_plan', plan_id=plan.id))
    
    form = TradePlanBeforeForm(obj=plan)
    
    if form.validate_on_submit():
        try:
            plan.symbol = form.symbol.data.upper().strip()
            plan.direction = form.direction.data
            plan.planned_entry = form.planned_entry.data
            plan.planned_stop_loss = form.planned_stop_loss.data
            plan.planned_take_profit = form.planned_take_profit.data
            plan.planned_lot_size = form.planned_lot_size.data
            plan.strategy = form.strategy.data
            plan.market_structure_confirmed = form.market_structure_confirmed.data
            plan.liquidity_taken = form.liquidity_taken.data
            plan.confirmation_candle_formed = form.confirmation_candle_formed.data
            plan.session_aligned = form.session_aligned.data
            plan.pre_trade_notes = form.pre_trade_notes.data
            
            # Recalculate
            plan.calculate_planned_rr()
            plan.calculate_plan_quality()
            
            # Handle new screenshot
            if form.screenshot_before.data:
                screenshot_path = save_screenshot(form.screenshot_before.data, 'before')
                if screenshot_path:
                    plan.screenshot_before_path = screenshot_path
            
            db.session.commit()
            flash('✅ Trade plan updated!', 'success')
            return redirect(url_for('planner.view_plan', plan_id=plan.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error: {str(e)}', 'danger')
    
    return render_template('planner/edit_plan.html', form=form, plan=plan)


# ==================== Delete Trade Plan ====================

@bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_plan(plan_id):
    """Delete trade plan"""
    plan = TradePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    
    try:
        db.session.delete(plan)
        db.session.commit()
        flash('✅ Trade plan deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('planner.index'))


# ==================== Legacy Routes (for backward compatibility) ====================

@bp.route('/create/<int:trade_id>', methods=['GET', 'POST'])
@login_required
def create_plan(trade_id):
    """Legacy: Create plan for existing trade - redirects to new workflow"""
    flash('Trade planning has been redesigned. Use the new Trade Planner.', 'info')
    return redirect(url_for('planner.new_plan'))


@bp.route('/view/<int:trade_id>')
@login_required
def view_plan_legacy(trade_id):
    """Legacy: View plan by trade_id"""
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
    """Legacy: Review trade - redirects to execute"""
    from app.models.trade import Trade
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    if trade.has_plan():
        plan = trade.get_plan()
        if plan:
            return redirect(url_for('planner.execute_plan', plan_id=plan.id))
    
    flash('No plan found for this trade.', 'warning')
    return redirect(url_for('planner.new_plan'))


# ==================== API: Calculate P&L ====================

@bp.route('/api/calculate-pnl', methods=['POST'])
@login_required
def api_calculate_pnl():
    """
    API endpoint to calculate P&L using the unified calculator
    Returns the same calculation that the backend uses
    """
    from app.utils.pnl_calculator import calculate_pnl
    
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper().strip()
        trade_type = data.get('trade_type', 'BUY').upper()
        entry_price = float(data.get('entry_price', 0))
        exit_price = float(data.get('exit_price', 0))
        lot_size = float(data.get('lot_size', 0.01))
        
        if not all([symbol, entry_price, exit_price, lot_size]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        pnl, pips, asset_desc = calculate_pnl(
            symbol=symbol,
            trade_type=trade_type,
            entry_price=entry_price,
            exit_price=exit_price,
            lot_size=lot_size
        )
        
        return jsonify({
            'success': True,
            'pnl': round(pnl, 2),
            'pips': round(pips, 1),
            'asset_type': asset_desc
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
