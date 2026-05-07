"""
Monetization Routes
Pricing, subscriptions, data export, and trial management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from datetime import datetime, timedelta
import csv
from io import StringIO, BytesIO
import os
from importlib import import_module
from flask_mail import Message
from app import mail

# Create Blueprint
bp = Blueprint('monetization', __name__, url_prefix='/monetization')


# ==================== Pricing ====================

@bp.route('/pricing')
def pricing():
    """
    Pricing Page
    
    Displays available subscription tiers
    """
    plans = [
        {
            'name': 'Free',
            'price': '$0',
            'period': '/month',
            'description': 'Perfect for getting started',
            'features': [
                'Unlimited trades',
                'Basic analytics',
                'Trade journaling',
                'AI feedback',
                'Community access'
            ],
            'cta': 'Current Plan' if not current_user.is_authenticated or current_user.subscription_tier == 'free' else 'Downgrade',
            'cta_disabled': True,
            'recommended': False
        },
        {
            'name': 'Pro',
            'price': '$5',
            'period': '/month',
            'description': 'Core analytics + enhanced tools (2-month trial for new users)',
            'features': [
                'Everything in Free',
                'Advanced analytics',
                'Performance charts',
                'Data export (CSV, JSON)',
                'API access',
                'Priority support'
            ],
            'cta': 'Upgrade Now',
            'cta_disabled': current_user.is_authenticated and current_user.subscription_tier == 'pro',
            'recommended': True
        },
        {
            'name': 'Pro Plus',
            'price': '$15',
            'period': '/month',
            'description': 'Full analytics suite + priority features',
            'features': [
                'Everything in Pro',
                'Advanced AI insights',
                'Custom dashboards & alerts',
                'Unlimited API calls',
                'Coach mode (coming soon)',
                'Dedicated support'
            ],
            'cta': 'Upgrade Now',
            'cta_disabled': current_user.is_authenticated and current_user.subscription_tier == 'pro_plus',
            'recommended': False
        }
    ]
    
    return render_template('monetization/pricing.html', plans=plans)


# ==================== Subscriptions ====================

@bp.route('/subscribe/<plan>', methods=['GET', 'POST'])
@login_required
def subscribe(plan):
    """
    Subscription Handler
    
    Initiates subscription to a plan
    TODO: Integrate with Stripe/PayPal
    """
    valid_plans = ('pro', 'pro_plus')
    if plan.lower() not in valid_plans:
        flash('❌ Invalid plan selected.', 'danger')
        return redirect(url_for('monetization.pricing'))

    # Dynamically import stripe and initialize
    try:
        stripe = import_module('stripe')
    except Exception:
        flash('⚠️ Payment gateway not available (stripe package not installed).', 'warning')
        return redirect(url_for('monetization.pricing'))

    stripe_key = current_app.config.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET_KEY')
    if not stripe_key:
        flash('⚠️ Payment gateway not configured. Ask the admin to set STRIPE_SECRET_KEY.', 'warning')
        return redirect(url_for('monetization.pricing'))

    stripe.api_key = stripe_key

    # Map plan to Stripe price IDs configured in app config or environment
    price_map = {
        'pro': current_app.config.get('STRIPE_PRICE_PRO') or os.environ.get('STRIPE_PRICE_PRO'),
        'pro_plus': current_app.config.get('STRIPE_PRICE_PRO_PLUS') or os.environ.get('STRIPE_PRICE_PRO_PLUS')
    }

    price_id = price_map.get(plan.lower())
    if not price_id:
        flash('⚠️ Price for selected plan is not configured.', 'warning')
        return redirect(url_for('monetization.pricing'))

    try:
        success_url = current_app.config.get('STRIPE_SUCCESS_URL') or url_for('dashboard.index', _external=True)
        cancel_url = current_app.config.get('STRIPE_CANCEL_URL') or url_for('monetization.pricing', _external=True)

        # Create a Stripe Checkout Session for subscription
        session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
        )

        # Redirect user to Stripe Checkout
        return redirect(session.url, code=303)
    except Exception:
        current_app.logger.exception("Subscription checkout error")
        flash('❌ Error initiating payment. Please try again later.', 'danger')
        return redirect(url_for('monetization.pricing'))


# ==================== Data Export ====================

@bp.route('/export-data')
@login_required
def export_data():
    """
    Export User Data
    
    Generates CSV export of all user trades and performance data
    """
    try:
        # Prepare CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['TradeVerse Data Export'])
        writer.writerow(['Exported', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['User', current_user.username])
        writer.writerow([])
        
        # Trades
        writer.writerow(['TRADES'])
        writer.writerow(['Date', 'Symbol', 'Type', 'Entry', 'Exit', 'P&L', 'Status', 'Notes'])
        
        trades = Trade.query.filter_by(user_id=current_user.id).all()
        for trade in trades:
            writer.writerow([
                trade.entry_time.strftime('%Y-%m-%d') if trade.entry_time else '',
                trade.symbol or '',
                trade.trade_type or '',
                f"${trade.entry_price:.2f}" if trade.entry_price else '',
                f"${trade.exit_price:.2f}" if trade.exit_price else '',
                f"${trade.pnl:.2f}" if trade.pnl else '',
                trade.status or '',
                trade.notes or ''
            ])
        
        writer.writerow([])
        writer.writerow(['TRADE PLANS'])
        writer.writerow(['Name', 'Trades Planned', 'Trades Executed', 'Status', 'Created', 'Updated'])
        
        plans = TradePlan.query.filter_by(user_id=current_user.id).all()
        for plan in plans:
            writer.writerow([
                plan.name or '',
                len(plan.trades) if plan.trades else 0,
                len([t for t in plan.trades if (t.status or '').upper() == 'CLOSED']) if plan.trades else 0,
                plan.status or '',
                plan.created_at.strftime('%Y-%m-%d') if plan.created_at else '',
                plan.updated_at.strftime('%Y-%m-%d') if plan.updated_at else ''
            ])
        
        # Convert to bytes and send as attachment
        csv_bytes = output.getvalue().encode('utf-8')
        mem = BytesIO(csv_bytes)
        mem.seek(0)

        filename = f"tradeverse_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        flash(f'❌ Error exporting data: {str(e)}', 'danger')
        current_app.logger.exception("Export data error")
        return redirect(url_for('dashboard.index'))


# ==================== Trial Management ====================

@bp.route('/trial-info')
@login_required
def trial_info():
    """
    Trial Information
    
    Shows remaining trial days and upgrade options
    """
    trial_days = 60
    days_used = (datetime.now() - current_user.created_at).days
    days_remaining = max(0, trial_days - days_used)
    trial_percent = min(100, (days_used / trial_days) * 100)
    
    return render_template('monetization/trial_info.html',
                         trial_days=trial_days,
                         days_used=days_used,
                         days_remaining=days_remaining,
                         trial_percent=trial_percent,
                         trial_expired=days_remaining == 0)



@bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Stripe Webhook endpoint
    Receives events from Stripe and updates user subscription status.
    """
    # Stripe webhook handling must be verified (no insecure fallbacks).
    try:
        stripe = import_module('stripe')
    except Exception:
        return jsonify({'ok': False, 'error': 'stripe package not installed'}), 500

    stripe_key = current_app.config.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET_KEY')
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET') or os.environ.get('STRIPE_WEBHOOK_SECRET')
    if not stripe_key or not webhook_secret:
        return jsonify({'ok': False, 'error': 'Stripe webhook not configured'}), 500

    stripe.api_key = stripe_key

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'ok': False}), 400

    # Idempotency: ignore duplicate event deliveries.
    try:
        from app.models.stripe_webhook_event import StripeWebhookEvent

        event_id = event.get("id")
        if event_id:
            existing = StripeWebhookEvent.query.filter_by(stripe_event_id=event_id).first()
            if existing:
                return jsonify({"received": True})
            db.session.add(
                StripeWebhookEvent(
                    stripe_event_id=event_id,
                    event_type=event.get("type"),
                )
            )
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Returning 500 tells Stripe to retry later.
        return jsonify({"ok": False, "error": "idempotency_store_failed"}), 500

    # Handle the checkout.session.completed event
    try:
        if event.get('type') == 'checkout.session.completed':
            session_obj = event['data']['object']
            customer_email = session_obj.get('customer_email')
            subscription_id = session_obj.get('subscription')

            # Attempt to update the user record
            if customer_email:
                from app.models.user import User
                user = User.query.filter_by(email=customer_email).first()
                if user:
                    # Determine plan by reading the subscription's items if available
                    plan_tier = None

                    try:
                        if subscription_id and stripe:
                            sub = stripe.Subscription.retrieve(subscription_id)
                            price_id = None
                            if sub and sub['items'] and sub['items']['data']:
                                price_id = sub['items']['data'][0]['price']['id']
                            # Map price_id to tier
                            if price_id == (current_app.config.get('STRIPE_PRICE_PRO') or os.environ.get('STRIPE_PRICE_PRO')):
                                plan_tier = 'pro'
                            elif price_id == (current_app.config.get('STRIPE_PRICE_ELITE') or os.environ.get('STRIPE_PRICE_ELITE')):
                                plan_tier = 'elite'
                    except Exception as e:
                        print(f"Error fetching subscription: {e}")

                    # Default to pro if unknown
                    user.subscription_tier = plan_tier or 'pro'
                    user.subscription_status = 'active'
                    user.subscription_expires_at = None
                    db.session.add(user)
                    db.session.commit()

                    # Payment confirmation email (best-effort)
                    try:
                        sender = current_app.config.get("MAIL_DEFAULT_SENDER")
                        if sender and user.email:
                            msg = Message(
                                subject="TradeVerse subscription activated",
                                sender=sender,
                                recipients=[user.email],
                            )
                            msg.body = (
                                f"Hi {user.username},\n\n"
                                f"Your TradeVerse subscription is now active: {user.subscription_tier}.\n\n"
                                "Thank you for supporting TradeVerse.\n"
                            )
                            mail.send(msg)
                    except Exception:
                        pass
        elif event.get('type') in ('invoice.payment_failed', 'customer.subscription.updated', 'customer.subscription.deleted'):
            obj = event.get('data', {}).get('object', {}) or {}
            customer_id = obj.get('customer') or obj.get('customer_id')
            if customer_id:
                from app.models.user import User
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user:
                    if event.get('type') == 'invoice.payment_failed':
                        user.subscription_status = 'past_due'
                    elif event.get('type') == 'customer.subscription.deleted':
                        user.subscription_status = 'canceled'
                        user.subscription_tier = 'free'
                    else:
                        status = (obj.get('status') or '').lower()
                        if status in ('active', 'trialing'):
                            user.subscription_status = status
                        elif status in ('past_due', 'canceled', 'cancelled', 'unpaid'):
                            user.subscription_status = 'past_due' if status == 'past_due' else 'canceled'
                    db.session.add(user)
                    db.session.commit()

    except Exception as e:
        print(f"Webhook handling error: {e}")
        # 500 so Stripe retries (webhook must be reliable)
        return jsonify({'ok': False}), 500

    return jsonify({'received': True})
