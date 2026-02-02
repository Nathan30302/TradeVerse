"""
Trade Routes
Trade logging, viewing, editing, and management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.trade import Trade
from app.models.trade_feedback import TradeFeedback
from app.models.cooldown import Cooldown, should_trigger_cooldown, get_cooldown_duration
from app.services.feedback_analyzer import generate_trade_feedback
from app.services.cooldown_manager import CooldownManager, get_active_cooldown, trigger_emotional_cooldown
from datetime import datetime
from werkzeug.utils import secure_filename
import os

# Create Blueprint
bp = Blueprint('trade', __name__, url_prefix='/trade')

# ==================== Helper Functions ====================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

# ==================== Add Trade ====================

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """
    Add New Trade
    
    Form to log a new trade with all details
    """
    # Check for active cooldown
    active_cooldown = get_active_cooldown(current_user.id)
    
    if request.method == 'POST':
        # Block if in cooldown (unless override)
        override = request.form.get('override_cooldown') == 'true'
        if active_cooldown and not override:
            flash('⏳ You are in a cooldown period. Please wait before trading.', 'warning')
            return redirect(url_for('trade.cooldown_status'))
        
        # Log override if used
        if active_cooldown and override:
            active_cooldown.override("User chose to override cooldown")
            flash('⚠️ Cooldown overridden. Please trade carefully!', 'warning')
        
        try:
            # Get basic trade info
            symbol = request.form.get('symbol', '').strip().upper()
            instrument_id = request.form.get('instrument_id')
            trade_type = request.form.get('trade_type', '').upper()
            lot_size = float(request.form.get('lot_size', 1.0))
            entry_price = float(request.form.get('entry_price'))
            
            # Get optional price levels
            exit_price = request.form.get('exit_price')
            stop_loss = request.form.get('stop_loss')
            take_profit = request.form.get('take_profit')
            
            # Get dates
            entry_date_str = request.form.get('entry_date')
            exit_date_str = request.form.get('exit_date')
            
            # Parse dates
            entry_date = datetime.fromisoformat(entry_date_str) if entry_date_str else datetime.utcnow()
            exit_date = datetime.fromisoformat(exit_date_str) if exit_date_str else None
            
            # Get strategy and session info
            strategy = request.form.get('strategy')
            session_type = request.form.get('session_type')
            timeframe = request.form.get('timeframe')
            
            # Get psychology
            emotion = request.form.get('emotion')
            confidence_level = request.form.get('confidence_level')
            
            # Get quality scores
            setup_quality = request.form.get('setup_quality')
            execution_quality = request.form.get('execution_quality')
            discipline_score = request.form.get('discipline_score')
            
            # Get notes
            pre_trade_plan = request.form.get('pre_trade_plan', '').strip()
            post_trade_notes = request.form.get('post_trade_notes', '').strip()
            
            # Get compliance
            checklist_completed = request.form.get('checklist_completed') == 'on'
            playbook_followed = request.form.get('playbook_followed') == 'on'
            
            # Get risk info
            commission = request.form.get('commission')
            swap = request.form.get('swap')
            
            # Create new trade
            trade = Trade(
                user_id=current_user.id,
                symbol=symbol,
                trade_type=trade_type,
                lot_size=lot_size,
                entry_price=entry_price,
                entry_date=entry_date,
                strategy=strategy,
                session_type=session_type,
                timeframe=timeframe,
                emotion=emotion,
                pre_trade_plan=pre_trade_plan if pre_trade_plan else None,
                post_trade_notes=post_trade_notes if post_trade_notes else None,
                checklist_completed=checklist_completed,
                playbook_followed=playbook_followed
            )

            # Attach instrument FK if provided
            if instrument_id:
                try:
                    trade.instrument_id = int(instrument_id)
                except ValueError:
                    pass
            
            # Set optional fields
            if exit_price:
                trade.exit_price = float(exit_price)
                trade.exit_date = exit_date
                trade.status = 'CLOSED'
            
            if stop_loss:
                trade.stop_loss = float(stop_loss)
            
            if take_profit:
                trade.take_profit = float(take_profit)
            
            if confidence_level:
                trade.confidence_level = int(confidence_level)
            
            if setup_quality:
                trade.setup_quality = int(setup_quality)
            
            if execution_quality:
                trade.execution_quality = int(execution_quality)
            
            if discipline_score:
                trade.discipline_score = int(discipline_score)
            
            if commission:
                trade.commission = float(commission)
            
            if swap:
                trade.swap = float(swap)
            
            # Calculate P/L and R:R if applicable
            if trade.exit_price:
                trade.calculate_pnl()
            
            if trade.stop_loss and trade.take_profit:
                trade.calculate_risk_reward()
            
            # Save to database
            db.session.add(trade)
            db.session.commit()
            
            # Check if emotion should trigger cooldown for next trade
            if emotion and should_trigger_cooldown(emotion):
                cooldown = trigger_emotional_cooldown(
                    current_user.id,
                    emotion,
                    f"Triggered after trading with emotion: {emotion}"
                )
                if cooldown:
                    flash(f'⏳ Cooldown activated ({cooldown.duration_minutes}min) due to {emotion}. Take a break!', 'warning')
            
            flash(f'✅ Trade {symbol} {trade_type} added successfully!', 'success')
            return redirect(url_for('trade.view', trade_id=trade.id))
            
        except ValueError as e:
            flash(f'❌ Invalid input: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error adding trade: {str(e)}', 'danger')
            print(f"Add trade error: {e}")
    
    return render_template('trade/add.html', active_cooldown=active_cooldown)


# ==================== Cooldown Status ====================

@bp.route('/cooldown')
@login_required
def cooldown_status():
    """
    Cooldown Status Page
    
    Shows current cooldown status and history
    """
    manager = CooldownManager(current_user.id)
    active_cooldown = manager.get_active_cooldown()
    cooldown_history = manager.get_cooldown_history(limit=10)
    stats = manager.get_cooldown_stats()
    
    return render_template('trade/cooldown.html',
                         active_cooldown=active_cooldown,
                         cooldown_history=cooldown_history,
                         stats=stats)


@bp.route('/cooldown/override', methods=['POST'])
@login_required
def override_cooldown():
    """Override active cooldown"""
    manager = CooldownManager(current_user.id)
    reason = request.form.get('reason', 'User override')
    
    if manager.override_cooldown(reason):
        flash('⚠️ Cooldown overridden. Please trade responsibly!', 'warning')
    else:
        flash('No active cooldown to override.', 'info')
    
    return redirect(url_for('trade.add'))


@bp.route('/api/cooldown-status')
@login_required
def cooldown_status_api():
    """API endpoint for cooldown status (for real-time updates)"""
    cooldown = get_active_cooldown(current_user.id)
    
    if cooldown:
        return jsonify(cooldown.to_dict())
    
    return jsonify({'is_active': False})

# ==================== View All Trades ====================

@bp.route('/list')
@login_required
def list():
    """
    View All Trades
    
    Displays list of all user's trades with filtering
    """
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    symbol_filter = request.args.get('symbol', '')
    strategy_filter = request.args.get('strategy', '')
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = Trade.query.filter_by(user_id=current_user.id)
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter_by(status=status_filter.upper())
    
    if symbol_filter:
        query = query.filter(Trade.symbol.contains(symbol_filter.upper()))
    
    if strategy_filter:
        query = query.filter_by(strategy=strategy_filter)
    
    # Order by most recent first
    query = query.order_by(Trade.entry_date.desc())
    
    # Paginate
    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    trades = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('trade/list.html', 
                         trades=trades,
                         status_filter=status_filter,
                         symbol_filter=symbol_filter,
                         strategy_filter=strategy_filter)

# ==================== View Single Trade ====================

@bp.route('/<int:trade_id>')
@login_required
def view(trade_id):
    """
    View Trade Details
    
    Displays full details of a single trade
    """
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    # Detect mistakes
    mistakes = trade.detect_mistakes()
    
    # Get AI feedback
    feedbacks = TradeFeedback.query.filter_by(trade_id=trade.id).order_by(TradeFeedback.feedback_type).all()
    
    return render_template('trade/view.html', trade=trade, mistakes=mistakes, feedbacks=feedbacks)


@bp.route('/<int:trade_id>/generate-feedback', methods=['POST'])
@login_required
def generate_feedback(trade_id):
    """
    Generate AI Feedback for a Trade
    
    Analyzes trade and creates automated feedback
    """
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    try:
        feedbacks = generate_trade_feedback(trade)
        flash(f'✅ Generated {len(feedbacks)} feedback items!', 'success')
    except Exception as e:
        flash(f'❌ Error generating feedback: {str(e)}', 'danger')
    
    return redirect(url_for('trade.view', trade_id=trade.id))

# ==================== Edit Trade ====================

@bp.route('/<int:trade_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(trade_id):
    """
    Edit Trade
    
    Modify existing trade details
    """
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        try:
            # Update basic info
            trade.symbol = request.form.get('symbol', '').strip().upper()
            # Update instrument_id if provided
            instrument_id = request.form.get('instrument_id')
            if instrument_id:
                try:
                    trade.instrument_id = int(instrument_id)
                except ValueError:
                    pass
            trade.trade_type = request.form.get('trade_type', '').upper()
            trade.lot_size = float(request.form.get('lot_size', 1.0))
            trade.entry_price = float(request.form.get('entry_price'))
            
            # Update optional fields
            exit_price = request.form.get('exit_price')
            if exit_price:
                trade.exit_price = float(exit_price)
                trade.status = 'CLOSED'
            
            stop_loss = request.form.get('stop_loss')
            trade.stop_loss = float(stop_loss) if stop_loss else None
            
            take_profit = request.form.get('take_profit')
            trade.take_profit = float(take_profit) if take_profit else None
            
            # Update strategy and session
            trade.strategy = request.form.get('strategy')
            trade.session_type = request.form.get('session_type')
            trade.timeframe = request.form.get('timeframe')
            
            # Update psychology
            trade.emotion = request.form.get('emotion')
            confidence_level = request.form.get('confidence_level')
            trade.confidence_level = int(confidence_level) if confidence_level else None
            
            # Update notes
            trade.pre_trade_plan = request.form.get('pre_trade_plan', '').strip() or None
            trade.post_trade_notes = request.form.get('post_trade_notes', '').strip() or None
            
            # Update compliance
            trade.checklist_completed = request.form.get('checklist_completed') == 'on'
            trade.playbook_followed = request.form.get('playbook_followed') == 'on'
            
            # Recalculate metrics
            if trade.exit_price:
                trade.calculate_pnl()
            
            if trade.stop_loss and trade.take_profit:
                trade.calculate_risk_reward()
            
            db.session.commit()
            
            flash('✅ Trade updated successfully!', 'success')
            return redirect(url_for('trade.view', trade_id=trade.id))
            
        except ValueError as e:
            flash(f'❌ Invalid input: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error updating trade: {str(e)}', 'danger')
            print(f"Edit trade error: {e}")
    
    return render_template('trade/edit.html', trade=trade)

# ==================== Delete Trade ====================

@bp.route('/<int:trade_id>/delete', methods=['POST'])
@login_required
def delete(trade_id):
    """
    Delete Trade
    
    Permanently remove a trade
    """
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    try:
        symbol = trade.symbol
        db.session.delete(trade)
        db.session.commit()
        flash(f'✅ Trade {symbol} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error deleting trade: {str(e)}', 'danger')
        print(f"Delete trade error: {e}")
    
    return redirect(url_for('trade.list'))

# ==================== Close Trade ====================

@bp.route('/<int:trade_id>/close', methods=['POST'])
@login_required
def close(trade_id):
    """
    Close Trade
    
    Close an open trade with exit price
    """
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    
    try:
        exit_price = float(request.form.get('exit_price'))
        exit_date_str = request.form.get('exit_date')
        
        exit_date = datetime.fromisoformat(exit_date_str) if exit_date_str else datetime.utcnow()
        
        trade.close_trade(exit_price, exit_date)
        
        result_emoji = trade.get_result_emoji()
        flash(f'{result_emoji} Trade closed! P/L: {trade.profit_loss:+.2f}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error closing trade: {str(e)}', 'danger')
        print(f"Close trade error: {e}")
    
    return redirect(url_for('trade.view', trade_id=trade.id))

# ==================== Quick Actions ====================

@bp.route('/quick-add', methods=['POST'])
@login_required
def quick_add():
    """
    Quick Add Trade
    
    Minimal form for quick trade logging (AJAX)
    """
    try:
        data = request.get_json()
        
        trade = Trade(
            user_id=current_user.id,
            symbol=data['symbol'].upper(),
            trade_type=data['trade_type'].upper(),
            entry_price=float(data['entry_price']),
            lot_size=float(data.get('lot_size', 1.0)),
            entry_date=datetime.utcnow()
        )
        
        db.session.add(trade)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Trade added successfully!',
            'trade_id': trade.id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400