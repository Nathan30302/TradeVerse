"""
Trade Routes
Trade logging, viewing, editing, and management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, Response, session
from flask_login import login_required, current_user
from app import db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.trade_feedback import TradeFeedback
from app.models.playbook_setup import PlaybookSetup
from app.models.cooldown import Cooldown, should_trigger_cooldown, get_cooldown_duration
from app.services.feedback_analyzer import generate_trade_feedback
from app.services.cooldown_manager import CooldownManager, get_active_cooldown, trigger_emotional_cooldown
from app.services.account_flags import current_user_exports_blocked
from app.services.entitlements import user_has_feature
from datetime import datetime
import csv
from io import StringIO
from sqlalchemy import or_
from sqlalchemy.orm import load_only
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
import os
from math import ceil
import builtins

# Create Blueprint
bp = Blueprint('trade', __name__, url_prefix='/trade')

# ==================== Helper Functions ====================

class _ManualPagination:
    """Minimal pagination object for templates when Query.paginate() can't be used safely."""

    def __init__(self, *, items, page: int, per_page: int, total: int):
        # trade.list route name shadows built-in list(); use builtins.list
        self.items = builtins.list(items)
        self.page = int(page)
        self.per_page = int(per_page)
        self.total = int(total)

    @property
    def pages(self) -> int:
        if self.total <= 0:
            return 0
        return int(ceil(self.total / self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(
        self,
        *,
        left_edge: int = 2,
        left_current: int = 2,
        right_current: int = 4,
        right_edge: int = 2,
    ):
        pages_end = self.pages + 1
        if pages_end == 1:
            return

        left_end = min(1 + left_edge, pages_end)
        yield from range(1, left_end)

        if left_end == pages_end:
            return

        mid_start = max(left_end, self.page - left_current)
        mid_end = min(self.page + right_current + 1, pages_end)

        if mid_start - left_end > 0:
            yield None

        yield from range(mid_start, mid_end)

        if mid_end == pages_end:
            return

        right_start = max(mid_end, pages_end - right_edge)

        if right_start - mid_end > 0:
            yield None

        yield from range(right_start, pages_end)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def _playbook_setups_for_trade_form():
    """Empty when Playbook migrations are not installed (avoids 500 on missing tables/columns)."""
    if not current_app.extensions.get('tradeverse_schema', {}).get('playbook_ready'):
        return []
    try:
        return (
            PlaybookSetup.query.filter_by(user_id=current_user.id, is_active=True)
            .order_by(PlaybookSetup.updated_at.desc().nullslast(), PlaybookSetup.created_at.desc())
            .all()
        )
    except Exception:
        current_app.logger.debug('PlaybookSetup list skipped (schema drift)', exc_info=True)
        return []


def _filtered_trades_query(user_id):
    """Build ordered query for trade list / CSV export (same filters as list view)."""
    status_filter = request.args.get('status', 'all')
    symbol_filter = request.args.get('symbol', '')
    strategy_filter = request.args.get('strategy', '')

    query = Trade.query.filter_by(user_id=user_id)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter.upper())
    if symbol_filter:
        query = query.filter(Trade.symbol.contains(symbol_filter.upper()))
    if strategy_filter:
        query = query.filter_by(strategy=strategy_filter)
    return query.order_by(Trade.entry_date.desc())

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
    accountability_required = bool(session.get("tv_accountability_required"))
    playbook_setups = _playbook_setups_for_trade_form()
    if request.method == 'GET':
        return render_template(
            'trade/add.html',
            active_cooldown=active_cooldown,
            prefill=None,
            accountability_required=accountability_required,
            playbook_setups=playbook_setups,
        )
    
    if request.method == 'POST':
        # Accountability mode: after overriding a cooldown, user must complete a checklist once.
        if accountability_required:
            confirmed = (request.form.get("accountability_confirmed") or "").lower() in ("1", "true", "yes", "on")
            if not confirmed:
                flash('Accountability mode: complete the pre-trade checklist before logging a trade.', 'warning')
                return render_template(
                    'trade/add.html',
                    active_cooldown=active_cooldown,
                    prefill=None,
                    accountability_required=True,
                    open_accountability_modal=True,
                    playbook_setups=playbook_setups,
                )

        # Block if in cooldown (unless override)
        override = request.form.get('override_cooldown') == 'true'
        if active_cooldown and not override:
            flash('⏳ Cooldown active. You can’t log a new trade until it expires (or override with a reason).', 'warning')
            # Keep user on Add Trade with an inline banner instead of redirecting away.
            return render_template(
                'trade/add.html',
                active_cooldown=active_cooldown,
                prefill=None,
                accountability_required=accountability_required,
                playbook_setups=playbook_setups,
            )
        
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
            log_status = (request.form.get('trade_log_status') or '').strip().lower()
            if log_status not in ('open', 'closed', ''):
                log_status = ''
            if not log_status:
                if exit_price and str(exit_price).strip():
                    log_status = 'closed'
                else:
                    log_status = 'open'

            # Get dates
            entry_date_str = request.form.get('entry_date')
            exit_date_str = request.form.get('exit_date')
            
            # Parse dates
            entry_date = datetime.fromisoformat(entry_date_str) if entry_date_str else datetime.utcnow()
            exit_date = datetime.fromisoformat(exit_date_str) if exit_date_str else None

            if log_status == 'open':
                exit_price = None
                exit_date = None
            elif log_status == 'closed' and not (exit_price and str(exit_price).strip()):
                flash('Closed trades need an exit price (or switch to Open).', 'danger')
                return render_template(
                    'trade/add.html',
                    active_cooldown=active_cooldown,
                    prefill=None,
                    accountability_required=accountability_required,
                    playbook_setups=playbook_setups,
                )
            
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

            if current_app.extensions.get('tradeverse_schema', {}).get('playbook_ready'):
                pb_setup_id = (request.form.get("playbook_setup_id") or "").strip()
                if pb_setup_id:
                    try:
                        pb_setup_id_int = int(pb_setup_id)
                        ok = PlaybookSetup.query.filter_by(id=pb_setup_id_int, user_id=current_user.id).first()
                        if ok:
                            trade.playbook_setup_id = pb_setup_id_int
                    except ValueError:
                        pass

            # Attach instrument FK if provided
            if instrument_id:
                try:
                    trade.instrument_id = int(instrument_id)
                except ValueError:
                    pass
            
            # Set optional fields
            if log_status == 'open':
                trade.exit_price = None
                trade.exit_date = None
                trade.status = 'OPEN'
            elif exit_price:
                trade.exit_price = float(exit_price)
                trade.exit_date = exit_date or datetime.utcnow()
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

            # Clear one-time accountability gate after successful log
            if session.get("tv_accountability_required"):
                session.pop("tv_accountability_required", None)

            # Trigger cooldowns (emotion-based and/or loss-streak)
            try:
                manager = CooldownManager(current_user.id)
                if emotion and should_trigger_cooldown(emotion):
                    cooldown = trigger_emotional_cooldown(
                        current_user.id,
                        emotion,
                        f"Triggered after trading with emotion: {emotion}"
                    )
                    if cooldown:
                        flash(f'⏳ Cooldown activated ({cooldown.duration_minutes}min) due to {emotion}. Take a break!', 'warning')
                else:
                    # If the trade was closed and ended as a loss, check for loss-streak cooldown.
                    if (trade.status or '').upper() == 'CLOSED' and (trade.profit_loss or 0) < 0:
                        ls = manager.trigger_loss_streak_cooldown(losses=2, duration_minutes=45)
                        if ls:
                            flash('⏳ Cooldown activated due to a loss streak. Step away and review before the next trade.', 'warning')
            except Exception:
                current_app.logger.debug("Cooldown trigger check failed", exc_info=True)
            
            flash(f'✅ Trade {symbol} {trade_type} added successfully!', 'success')
            return redirect(url_for('trade.view', trade_id=trade.id))
            
        except ValueError as e:
            flash(f'❌ Invalid input: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Add trade error: {e}")
            flash(f'❌ Error adding trade: {str(e)}', 'danger')

    prefill = None
    if request.method == 'GET' and request.args.get('duplicate') in ('1', 'true', 'yes'):
        prefill = _duplicate_prefill(current_user.id)
        if prefill:
            flash('Fields pre-filled from your most recent trade. Update prices and save.', 'info')
        else:
            flash('No previous trade to duplicate yet.', 'info')

    return render_template(
        'trade/add.html',
        active_cooldown=active_cooldown,
        prefill=prefill,
        playbook_setups=playbook_setups,
        accountability_required=accountability_required,
    )


def _duplicate_prefill(user_id):
    """Field dict to pre-fill Add Trade from the user's most recent trade."""
    last_trade = (
        Trade.query.filter_by(user_id=user_id)
        .order_by(Trade.entry_date.desc().nullslast(), Trade.id.desc())
        .first()
    )
    if not last_trade:
        return None
    return {
        'symbol': last_trade.symbol,
        'instrument_id': last_trade.instrument_id,
        'trade_type': last_trade.trade_type,
        'lot_size': last_trade.lot_size,
        'entry_price': last_trade.entry_price,
        'stop_loss': last_trade.stop_loss,
        'take_profit': last_trade.take_profit,
        'strategy': last_trade.strategy or '',
        'session_type': last_trade.session_type or '',
        'timeframe': last_trade.timeframe or '',
        'pre_trade_plan': last_trade.pre_trade_plan or '',
    }


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
    reason = (request.form.get('reason') or '').strip()
    if not reason or len(reason) < 8:
        flash('Please enter a short reason (at least 8 characters) to override.', 'warning')
        return redirect(url_for('trade.add'))

    if not manager.can_override_now(max_per_day=1, max_per_week=3):
        flash('Override limit reached. Max 1 per day and 3 per week.', 'warning')
        return redirect(url_for('trade.add'))

    if manager.override_cooldown(reason):
        # Premium: accountability mode — require a pre-trade checklist once after override
        session["tv_accountability_required"] = True
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
    status_filter = request.args.get('status', 'all')
    symbol_filter = request.args.get('symbol', '')
    strategy_filter = request.args.get('strategy', '')
    page = request.args.get('page', 1, type=int)

    query = _filtered_trades_query(current_user.id)

    # IMPORTANT: when the DB schema is behind migrations, Query.count() used by
    # Flask-SQLAlchemy pagination can SELECT missing columns (e.g. playbook_setup_id)
    # even though it's "just" a count. Restrict the query columns to the ones this
    # page actually needs.
    query = query.options(
        load_only(
            Trade.id,
            Trade.entry_date,
            Trade.symbol,
            Trade.emotion,
            Trade.trade_type,
            Trade.entry_price,
            Trade.exit_price,
            Trade.lot_size,
            Trade.profit_loss,
            Trade.risk_reward,
            Trade.strategy,
            Trade.status,
        )
    )

    # Paginate (manual): Flask-SQLAlchemy Query.paginate() calls Query.count(),
    # which can SELECT missing columns when migrations lag behind prod DB.
    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    offset = max(0, (page - 1) * per_page)
    items = query.limit(per_page).offset(offset).all()
    total = int(query.order_by(None).with_entities(Trade.id).count() or 0)
    trades = _ManualPagination(items=items, page=page, per_page=per_page, total=total)

    return render_template('trade/list.html',
                           trades=trades,
                           status_filter=status_filter,
                           symbol_filter=symbol_filter,
                           strategy_filter=strategy_filter)


@bp.route('/export.csv')
@login_required
def list_export_csv():
    """Export trades matching current list filters as CSV."""
    if not user_has_feature(current_user, 'exports'):
        flash(
            'CSV export is included with Pro and Pro Plus (and during eligible trials). '
            'Upgrade to download your trades.',
            'warning',
        )
        return redirect(url_for('main.pricing'))

    if current_user_exports_blocked(current_user):
        flash(
            "CSV export is temporarily disabled for this account. Contact support if this is unexpected.",
            "danger",
        )
        return redirect(url_for('trade.list'))

    def _csv_dt(val):
        if val is None:
            return ''
        if hasattr(val, 'isoformat'):
            try:
                return val.isoformat()
            except Exception:
                return str(val)
        return str(val)

    try:
        try:
            db.session.rollback()
        except Exception:
            pass

        query = _filtered_trades_query(current_user.id)
        trades = query.all()

        buf = StringIO()
        w = csv.writer(buf)
        w.writerow([
            'id', 'symbol', 'trade_type', 'status', 'entry_date', 'exit_date',
            'entry_price', 'exit_price', 'stop_loss', 'take_profit', 'lot_size',
            'profit_loss', 'risk_reward', 'strategy', 'emotion', 'session_type'
        ])
        for t in trades:
            w.writerow([
                t.id,
                t.symbol or '',
                t.trade_type or '',
                t.status or '',
                _csv_dt(t.entry_date),
                _csv_dt(t.exit_date),
                t.entry_price if t.entry_price is not None else '',
                t.exit_price if t.exit_price is not None else '',
                t.stop_loss if t.stop_loss is not None else '',
                t.take_profit if t.take_profit is not None else '',
                t.lot_size if t.lot_size is not None else '',
                t.profit_loss if t.profit_loss is not None else '',
                t.risk_reward if t.risk_reward is not None else '',
                t.strategy or '',
                t.emotion or '',
                t.session_type or '',
            ])

        resp = Response(buf.getvalue(), mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = 'attachment; filename="tradeverse-trades.csv"'
        return resp
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.exception('Trade CSV export failed: %s', exc)
        flash('Could not generate CSV. Please try again or contact support.', 'danger')
        return redirect(url_for('trade.list'))

# ==================== View Single Trade ====================

@bp.route('/<int:trade_id>')
@login_required
def view(trade_id):
    """
    View Trade Details
    
    Displays full details of a single trade
    """
    try:
        trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()

        linked_plans = TradePlan.query.filter(
            TradePlan.user_id == current_user.id,
            or_(TradePlan.executed_trade_id == trade.id, TradePlan.trade_id == trade.id)
        ).order_by(TradePlan.created_at.desc()).all()

        # Detect mistakes safely
        mistakes = []
        try:
            mistakes = trade.detect_mistakes()
        except Exception as e:
            current_app.logger.error(f"Error detecting mistakes for trade {trade_id}: {e}")
        
        # Get AI feedback safely
        feedbacks = []
        try:
            feedbacks = TradeFeedback.query.filter_by(trade_id=trade.id).order_by(TradeFeedback.feedback_type).all()
        except Exception as e:
            current_app.logger.error(f"Error fetching feedback for trade {trade_id}: {e}")
        
        return render_template(
            'trade/view.html',
            trade=trade,
            mistakes=mistakes,
            feedbacks=feedbacks,
            linked_plans=linked_plans,
        )

    except HTTPException:
        # Preserve real 404/403 responses — do not flash a misleading DB/template error.
        raise
    except Exception:
        # Clear any aborted transaction state before redirecting.
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.exception("Error viewing trade %s", trade_id)
        flash('❌ Error loading trade details. Please try again.', 'danger')
        return redirect(url_for('trade.list'))


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
    playbook_setups = _playbook_setups_for_trade_form()
    
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
                if not trade.exit_date:
                    trade.exit_date = datetime.utcnow()
            else:
                trade.exit_price = None
                trade.exit_date = None
                trade.status = 'OPEN'
            
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

            if current_app.extensions.get('tradeverse_schema', {}).get('playbook_ready'):
                pb_setup_id = (request.form.get("playbook_setup_id") or "").strip()
                if pb_setup_id:
                    try:
                        pb_setup_id_int = int(pb_setup_id)
                        ok = PlaybookSetup.query.filter_by(id=pb_setup_id_int, user_id=current_user.id).first()
                        trade.playbook_setup_id = pb_setup_id_int if ok else None
                    except ValueError:
                        trade.playbook_setup_id = None
                else:
                    trade.playbook_setup_id = None
            
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
            current_app.logger.exception("Edit trade error")
    
    return render_template('trade/edit.html', trade=trade, playbook_setups=playbook_setups)

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
        current_app.logger.exception("Delete trade error")
    
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
        current_app.logger.exception("Close trade error")
    
    return redirect(url_for('trade.view', trade_id=trade.id, review=1))

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
        }), 