"""
Monetization Routes
Pricing, subscriptions, data export, and trial management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from datetime import datetime
import csv
from io import StringIO, BytesIO
import os
from importlib import import_module

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
            'price': '$9',
            'period': '/month',
            'description': 'For serious traders',
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
            'name': 'Elite',
            'price': '$29',
            'period': '/month',
            'description': 'For professionals',
            'features': [
                'Everything in Pro',
                'Advanced AI insights',
                'Custom dashboards',
                'Unlimited API calls',
                'Team collaboration',
                'Dedicated support'
            ],
            'cta': 'Upgrade Now',
            'cta_disabled': current_user.is_authenticated and current_user.subscription_tier == 'elite',
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
    valid_plans = ('pro', 'elite')
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
        'elite': current_app.config.get('STRIPE_PRICE_ELITE') or os.environ.get('STRIPE_PRICE_ELITE')
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
    except Exception as e:
        print(f"Subscription error: {e}")
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
                len([t for t in plan.trades if t.status == 'closed']) if plan.trades else 0,
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
        print(f"Export error: {e}")
        return redirect(url_for('dashboard.index'))


# ==================== Trial Management ====================

@bp.route('/trial-info')
@login_required
def trial_info():
    """
    Trial Information
    
    Shows remaining trial days and upgrade options
    """
    trial_days = 30
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
    # Dynamically import stripe if available
    try:
        stripe = import_module('stripe')
    except Exception:
        stripe = None

    stripe_key = current_app.config.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET_KEY')
    if stripe_key and stripe:
        stripe.api_key = stripe_key

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET') or os.environ.get('STRIPE_WEBHOOK_SECRET')

    try:
        if webhook_secret:
            if not stripe:
                print("Webhook verification requested but stripe package not available")
                return jsonify({'ok': False}), 400
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            event = request.get_json()
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'ok': False}), 400

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

    except Exception as e:
        print(f"Webhook handling error: {e}")

    return jsonify({'received': True})
