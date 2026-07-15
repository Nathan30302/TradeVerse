"""
Monetization Routes
Pricing, subscriptions, data export, and trial management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db, csrf
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from datetime import datetime, timedelta, timezone
import csv
from io import StringIO, BytesIO
import os
from importlib import import_module
from flask_mail import Message
from app import mail
from app.services.account_flags import current_user_exports_blocked
from app.services.entitlements import _safe_getattr, user_has_feature
import secrets
from sqlalchemy import text

# Create Blueprint
bp = Blueprint('monetization', __name__, url_prefix='/monetization')


# ==================== Pricing ====================

def render_pricing_page():
    """
    Authenticated pricing page HTML.

    Canonical URL is ``/pricing`` (``main.pricing``). The legacy URL
    ``/monetization/pricing`` issues a 301 for old internal links.
    """
    current_tier = "free"
    if current_user.is_authenticated:
        try:
            current_tier = (current_user.effective_subscription().tier or "free").lower()
        except Exception:
            current_tier = "free"

    # Feature gates are defined in app/services/entitlements.py (FEATURES_BY_TIER).
    # Keep marketing bullets aligned with those tiers so the page matches actual access.
    trial_days_new_accounts = int(os.environ.get('TV_TRIAL_DAYS_PRO_PLUS', '60') or '60')
    extended_promo = (os.environ.get('TV_ALL_USERS_PROPLUS_TRIAL', '1') or '1').strip().lower() in {
        '1', 'true', 'yes', 'on',
    }

    plans = [
        {
            'name': 'Free',
            'slug': 'free',
            'price': '$0',
            'period': '/month',
            'description': 'Journal trades with core dashboard stats',
            'features': [
                'Trading journal & trade history',
                'Playbook setups (rules, checklists, example charts)',
                'Dashboard overview & core statistics',
                'Basic analytics views',
            ],
            'cta': 'Current Plan' if (not current_user.is_authenticated or current_tier == 'free') else 'Downgrade',
            'cta_disabled': True,
            'recommended': False,
        },
        {
            'name': 'Pro',
            'slug': 'pro',
            'price': '$5',
            'period': '/month',
            'description': 'Advanced analytics, exports, and broker API imports',
            'features': [
                'Everything in Free',
                'Advanced analytics (metrics API: expectancy, drawdown, R)',
                'Export trades & data (CSV / JSON)',
                'Broker API imports',
            ],
            'cta': 'Upgrade Now',
            'cta_disabled': current_user.is_authenticated and current_tier == 'pro',
            'recommended': True,
        },
        {
            'name': 'Pro Plus',
            'slug': 'pro_plus',
            'price': '$15',
            'period': '/month',
            'description': 'Full Pro feature set plus coach-mode tier',
            'features': [
                'Everything in Pro',
                'Coach mode & premium coaching track (rolled out in-app)',
                'Strategy Lab (plain-English setup scoring)',
            ],
            'cta': 'Upgrade Now',
            'cta_disabled': current_user.is_authenticated and current_tier == 'pro_plus',
            'recommended': False,
        },
    ]

    return render_template(
        'monetization/pricing.html',
        plans=plans,
        trial_days_new_accounts=trial_days_new_accounts,
        extended_promo_active=extended_promo,
    )


@bp.route('/pricing')
def pricing():
    """Legacy path: consolidate on ``/pricing`` for indexing and internal links."""
    return redirect(url_for('main.pricing'), code=301)


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
        return redirect(url_for('main.pricing'))

    # Prefer Paytiko if configured (global orchestration like AquaFunded).
    paytiko_secret = current_app.config.get("PAYTIKO_MERCHANT_SECRET_KEY") or os.environ.get("PAYTIKO_MERCHANT_SECRET_KEY")
    paytiko_core_url = current_app.config.get("PAYTIKO_CORE_URL") or os.environ.get("PAYTIKO_CORE_URL")
    paytiko_currency = (current_app.config.get("PAYTIKO_DEFAULT_CURRENCY") or os.environ.get("PAYTIKO_DEFAULT_CURRENCY") or "USD").upper()
    if paytiko_secret and paytiko_core_url:
        try:
            requests = import_module("requests")
        except Exception:
            flash("⚠️ Payment gateway not available (requests package missing).", "warning")
            return redirect(url_for("main.pricing"))

        # Amounts should match the pricing page.
        amount_map = {"pro": 5, "pro_plus": 15}
        amount = amount_map.get(plan.lower())
        if amount is None:
            flash("❌ Invalid plan selected.", "danger")
            return redirect(url_for("main.pricing"))

        # Paytiko signature: sha256("{email};{timestamp};{merchant_secret}")
        ts = int(datetime.now(timezone.utc).timestamp())
        email = (current_user.email or "").strip()
        signature = __import__("hashlib").sha256(f"{email};{ts};{paytiko_secret}".encode("utf-8")).hexdigest()

        # Encode user + plan in OrderId so webhook can update the right account.
        order_id = f"tvsub-{current_user.id}-{plan.lower()}-{secrets.token_hex(4)}"

        webhook_url = current_app.config.get("PAYTIKO_WEBHOOK_URL") or os.environ.get("PAYTIKO_WEBHOOK_URL") or url_for("monetization.paytiko_webhook", _external=True)
        success_url = current_app.config.get("PAYTIKO_SUCCESS_REDIRECT_URL") or os.environ.get("PAYTIKO_SUCCESS_REDIRECT_URL") or url_for("monetization.paytiko_success", _external=True)
        failed_url = current_app.config.get("PAYTIKO_FAILED_REDIRECT_URL") or os.environ.get("PAYTIKO_FAILED_REDIRECT_URL") or url_for("monetization.paytiko_failed", _external=True)

        payload = {
            "Timestamp": ts,
            "OrderId": order_id,
            "Signature": signature,
            "BillingDetails": {
                "FirstName": (current_user.username or "Trader")[:255],
                "LastName": "",
                "Email": email,
                # Paytiko expects ISO-3166 alpha-2.
                "Country": (os.environ.get("PAYTIKO_DEFAULT_COUNTRY") or "ZM")[:2].upper(),
                "Phone": (getattr(current_user, "phone", None) or os.environ.get("SUPPORT_PHONE") or "+260")[:20],
                "Currency": paytiko_currency,
                # lock the amount on hosted page (per Paytiko request shape used by integrations)
                "LockedAmount": int(amount),
            },
            "WebhookUrl": webhook_url,
            "SuccessRedirectUrl": success_url,
            "FailedRedirectUrl": failed_url,
            "CashierDescription": f"TradeVerse {plan.lower()} subscription",
        }

        try:
            core = paytiko_core_url.rstrip("/")
            resp = requests.post(
                f"{core}/api/payment/hosted-page",
                json=payload,
                headers={"Content-Type": "application/json", "X-Merchant-Secret": paytiko_secret},
                timeout=20,
            )
            data = resp.json() if resp.content else {}
            redirect_url = (data or {}).get("redirectUrl") or (data or {}).get("redirect_url")
            if resp.status_code >= 400 or not redirect_url:
                current_app.logger.warning("Paytiko init failed: status=%s body=%s", resp.status_code, data)
                flash("❌ Error initiating payment. Please try again later.", "danger")
                return redirect(url_for("main.pricing"))
            return redirect(redirect_url, code=303)
        except Exception:
            current_app.logger.exception("Paytiko checkout error")
            flash("❌ Error initiating payment. Please try again later.", "danger")
            return redirect(url_for("main.pricing"))

    # Prefer Flutterwave if configured (works in more African countries).
    flw_secret = current_app.config.get('FLW_SECRET_KEY') or os.environ.get('FLW_SECRET_KEY')
    flw_public = current_app.config.get('FLW_PUBLIC_KEY') or os.environ.get('FLW_PUBLIC_KEY')
    flw_currency = (current_app.config.get('FLW_CURRENCY') or os.environ.get('FLW_CURRENCY') or 'USD').upper()
    if flw_secret and flw_public:
        try:
            requests = import_module('requests')
        except Exception:
            flash('⚠️ Payment gateway not available (requests package missing).', 'warning')
            return redirect(url_for('main.pricing'))

        # Amounts should match the pricing page.
        amount_map = {'pro': 5, 'pro_plus': 15}
        amount = amount_map.get(plan.lower())
        if amount is None:
            flash('❌ Invalid plan selected.', 'danger')
            return redirect(url_for('main.pricing'))

        tx_ref = f"tv_{current_user.id}_{plan.lower()}_{secrets.token_urlsafe(10)}"
        redirect_url = url_for('monetization.flutterwave_callback', _external=True)
        cancel_url = current_app.config.get('FLW_CANCEL_URL') or os.environ.get('FLW_CANCEL_URL') or url_for('main.pricing', _external=True)

        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": flw_currency,
            "redirect_url": redirect_url,
            "customer": {"email": current_user.email, "name": current_user.username},
            "meta": {"user_id": current_user.id, "plan": plan.lower()},
            "customizations": {"title": "TradeVerse", "description": f"TradeVerse {plan.lower()} subscription"},
        }

        # Optional recurring payment plan IDs set in Flutterwave dashboard.
        plan_id_env = {
            "pro": current_app.config.get("FLW_PLAN_PRO") or os.environ.get("FLW_PLAN_PRO"),
            "pro_plus": current_app.config.get("FLW_PLAN_PRO_PLUS") or os.environ.get("FLW_PLAN_PRO_PLUS"),
        }.get(plan.lower())
        if plan_id_env:
            payload["payment_plan"] = plan_id_env

        try:
            resp = requests.post(
                "https://api.flutterwave.com/v3/payments",
                json=payload,
                headers={"Authorization": f"Bearer {flw_secret}"},
                timeout=20,
            )
            data = resp.json() if resp.content else {}
            link = (data or {}).get("data", {}).get("link")
            if resp.status_code >= 400 or not link:
                current_app.logger.warning("Flutterwave init failed: status=%s body=%s", resp.status_code, data)
                flash('❌ Error initiating payment. Please try again later.', 'danger')
                return redirect(cancel_url)
            return redirect(link, code=303)
        except Exception:
            current_app.logger.exception("Flutterwave checkout error")
            flash('❌ Error initiating payment. Please try again later.', 'danger')
            return redirect(url_for('main.pricing'))

    # Fallback: Stripe (if configured)
    try:
        stripe = import_module('stripe')
    except Exception:
        flash('⚠️ Payment gateway not configured yet. Please contact support.', 'warning')
        return redirect(url_for('main.pricing'))

    stripe_key = current_app.config.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET_KEY')
    if not stripe_key:
        flash('⚠️ Payment gateway not configured yet. Please contact support.', 'warning')
        return redirect(url_for('main.pricing'))

    stripe.api_key = stripe_key

    price_map = {
        'pro': current_app.config.get('STRIPE_PRICE_PRO') or os.environ.get('STRIPE_PRICE_PRO'),
        'pro_plus': current_app.config.get('STRIPE_PRICE_PRO_PLUS') or os.environ.get('STRIPE_PRICE_PRO_PLUS')
    }
    price_id = price_map.get(plan.lower())
    if not price_id:
        flash('⚠️ Price for selected plan is not configured.', 'warning')
        return redirect(url_for('main.pricing'))

    try:
        success_url = current_app.config.get('STRIPE_SUCCESS_URL') or url_for('dashboard.index', _external=True)
        cancel_url = current_app.config.get('STRIPE_CANCEL_URL') or url_for('main.pricing', _external=True)
        session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
        )
        return redirect(session.url, code=303)
    except Exception:
        current_app.logger.exception("Subscription checkout error")
        flash('❌ Error initiating payment. Please try again later.', 'danger')
        return redirect(url_for('main.pricing'))


@bp.route("/paytiko/success")
@login_required
def paytiko_success():
    flash("✅ Payment received. Activating your subscription…", "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/paytiko/failed")
@login_required
def paytiko_failed():
    flash("Payment not completed. Please try again.", "warning")
    return redirect(url_for("main.pricing"))


@bp.route("/paytiko/webhook", methods=["POST"])
@csrf.exempt
def paytiko_webhook():
    """
    Paytiko webhook: verifies payload signature and updates subscription status.
    Signature is expected in payload['Signature'] and is sha256(\"{merchant_secret}:{order_id}\").
    """
    paytiko_secret = current_app.config.get("PAYTIKO_MERCHANT_SECRET_KEY") or os.environ.get("PAYTIKO_MERCHANT_SECRET_KEY")
    if not paytiko_secret:
        return jsonify({"ok": False}), 500

    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    order_id = payload.get("OrderId") or payload.get("orderId") or ""
    sig = payload.get("Signature") or payload.get("signature") or ""
    if not order_id or not sig:
        return jsonify({"ok": False}), 400

    expected = __import__("hashlib").sha256(f"{paytiko_secret}:{order_id}".encode("utf-8")).hexdigest()
    if expected != sig:
        return jsonify({"ok": False}), 400

    status = (payload.get("TransactionStatus") or payload.get("transactionStatus") or "").upper()
    # We only act on successful SALE-like events.
    if status not in {"SUCCESS", "SUCCESSFUL", "APPROVED", "OK"}:
        return jsonify({"ok": True})

    # Extract user_id and plan from order id: tvsub-<uid>-<plan>-<rand>
    plan = "pro"
    user_id = None
    try:
        parts = str(order_id).split("-")
        if len(parts) >= 4 and parts[0] == "tvsub":
            user_id = int(parts[1])
            plan = (parts[2] or "pro").lower()
    except Exception:
        user_id = None

    if plan not in {"pro", "pro_plus"}:
        plan = "pro"

    if not user_id:
        return jsonify({"ok": True})

    try:
        from app.models.user import User

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"ok": True})
        user.subscription_tier = plan
        user.subscription_status = "active"
        user.subscription_expires_at = None
        db.session.add(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Paytiko webhook failed to update user")
        return jsonify({"ok": True})

    return jsonify({"ok": True})


@bp.route('/flutterwave/callback')
@login_required
def flutterwave_callback():
    """
    Flutterwave redirect/callback after hosted checkout.
    We verify the transaction server-side and then update the user's tier.
    """
    flw_secret = current_app.config.get('FLW_SECRET_KEY') or os.environ.get('FLW_SECRET_KEY')
    if not flw_secret:
        flash('⚠️ Payment verification unavailable. Please contact support.', 'warning')
        return redirect(url_for('dashboard.index'))

    status = (request.args.get("status") or "").lower()
    tx_ref = request.args.get("tx_ref") or ""
    transaction_id = request.args.get("transaction_id") or ""

    # If user cancelled, go back to pricing.
    if status in {"cancelled", "canceled"}:
        flash("Payment cancelled.", "info")
        return redirect(url_for("main.pricing"))

    if not transaction_id:
        flash("Could not verify payment. Please contact support.", "warning")
        return redirect(url_for("main.pricing"))

    try:
        requests = import_module("requests")
        vr = requests.get(
            f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
            headers={"Authorization": f"Bearer {flw_secret}"},
            timeout=20,
        )
        data = vr.json() if vr.content else {}
        d = (data or {}).get("data") or {}
        verified_status = (d.get("status") or "").lower()
        charge_tx_ref = d.get("tx_ref") or ""
        meta = d.get("meta") or {}
        paid_amount = d.get("amount")
        currency = (d.get("currency") or "").upper()
    except Exception:
        current_app.logger.exception("Flutterwave verify failed")
        flash("Could not verify payment. Please try again.", "warning")
        return redirect(url_for("main.pricing"))

    if verified_status != "successful":
        flash("Payment not completed.", "warning")
        return redirect(url_for("main.pricing"))

    # Trust meta plan if present; fall back to parsing our tx_ref.
    plan = (meta.get("plan") or "").lower()
    if plan not in {"pro", "pro_plus"}:
        for p in ("pro_plus", "pro"):
            if f"_{p}_" in (charge_tx_ref or tx_ref):
                plan = p
                break
    if plan not in {"pro", "pro_plus"}:
        plan = "pro"

    # Update user subscription fields.
    try:
        current_user.subscription_tier = plan
        current_user.subscription_status = "active"
        current_user.subscription_expires_at = None
        if not _safe_getattr(current_user, "stripe_customer_id", None):
            # Keep this column as a generic "customer id" if present in schema; if missing it will be stripped by orm hooks.
            pass
        db.session.add(current_user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to persist Flutterwave subscription state")
        flash("Payment succeeded, but we couldn't update your account yet. Contact support.", "warning")
        return redirect(url_for("dashboard.index"))

    flash(f"✅ Subscription activated: {plan.replace('_', ' ').title()}", "success")
    return redirect(url_for("dashboard.index"))


@bp.route('/flutterwave/webhook', methods=['POST'])
@csrf.exempt
def flutterwave_webhook():
    """
    Flutterwave webhook.
    Verify using the `verif-hash` header (set in Flutterwave dashboard).
    """
    expected = current_app.config.get("FLW_WEBHOOK_HASH") or os.environ.get("FLW_WEBHOOK_HASH")
    got = request.headers.get("verif-hash") or request.headers.get("Verif-Hash") or ""
    if expected and got != expected:
        return jsonify({"ok": False}), 401

    payload = request.get_json(silent=True) or {}
    event = (payload.get("event") or payload.get("type") or "").lower()
    data = payload.get("data") or {}

    # Best-effort: if we can link an email to a user, mark active.
    try:
        if event in {"charge.completed", "payment.completed"}:
            customer = (data.get("customer") or {}) if isinstance(data, dict) else {}
            email = (customer.get("email") or "").strip().lower()
            meta = data.get("meta") or {}
            plan = (meta.get("plan") or "").lower()
            if plan not in {"pro", "pro_plus"}:
                plan = "pro"
            if email:
                from app.models.user import User
                user = User.query.filter(func.lower(User.email) == email).first()
                if user:
                    user.subscription_tier = plan
                    user.subscription_status = "active"
                    user.subscription_expires_at = None
                    db.session.add(user)
                    db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Flutterwave webhook processing failed")
        # Return 200 anyway so Flutterwave doesn't hammer retries forever.
        return jsonify({"ok": True})

    return jsonify({"ok": True})


# ==================== Data Export ====================

@bp.route('/export-data')
@login_required
def export_data():
    """
    Export User Data
    
    Generates CSV export of all user trades and performance data
    """
    if not user_has_feature(current_user, 'exports'):
        flash(
            'Full data export is included with Pro and Pro Plus (and during trials). '
            'Upgrade to download your trades and plans as CSV.',
            'warning',
        )
        return redirect(url_for('main.pricing'))

    if current_user_exports_blocked(current_user):
        flash(
            "Data export is temporarily disabled for this account. Contact support if this is unexpected.",
            "danger",
        )
        return redirect(url_for('dashboard.index'))
    try:
        # Prepare CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['TradeVerse Data Export'])
        writer.writerow(['Exported', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['User', current_user.username])
        writer.writerow([])
        
        # Trades (columns match Trade model — not legacy aliases like entry_time / pnl / notes)
        writer.writerow(['TRADES'])
        writer.writerow(
            [
                'Entry date',
                'Symbol',
                'Type',
                'Entry',
                'Exit',
                'P&L',
                'Status',
                'Strategy',
                'Notes',
            ]
        )

        trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()

        def _trade_notes_row(t: Trade) -> str:
            parts = [t.pre_trade_plan, t.post_trade_notes, t.mistakes, t.lessons_learned]
            s = ' | '.join(p.strip() for p in parts if p and str(p).strip())
            return s[:4000] if s else ''

        for trade in trades:
            ed = trade.entry_date
            pl = trade.profit_loss
            writer.writerow(
                [
                    ed.strftime('%Y-%m-%d %H:%M') if ed else '',
                    trade.symbol or '',
                    trade.trade_type or '',
                    f'{trade.entry_price:.5f}' if trade.entry_price is not None else '',
                    f'{trade.exit_price:.5f}' if trade.exit_price is not None else '',
                    f'{pl:.2f}' if pl is not None else '',
                    trade.status or '',
                    trade.strategy or '',
                    _trade_notes_row(trade),
                ]
            )

        writer.writerow([])
        writer.writerow(['TRADE PLANS'])
        writer.writerow(
            [
                'Label',
                'Plan rows',
                'Executed',
                'Status',
                'Created',
                'Updated',
            ]
        )

        plans = TradePlan.query.filter_by(user_id=current_user.id).order_by(TradePlan.created_at.desc()).all()
        for plan in plans:
            label = (f"{plan.symbol} {plan.direction}".strip() if plan.symbol else f"Plan #{plan.id}")
            st = (plan.status or '').upper()
            executed_flag = bool(
                plan.executed
                or st in {'EXECUTED', 'REVIEWED'}
                or plan.executed_trade_id is not None
            )
            writer.writerow(
                [
                    label,
                    1,
                    1 if executed_flag else 0,
                    plan.status or '',
                    plan.created_at.strftime('%Y-%m-%d') if plan.created_at else '',
                    plan.updated_at.strftime('%Y-%m-%d') if plan.updated_at else '',
                ]
            )
        
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
    from app.services.entitlements import get_effective_subscription_state

    state = get_effective_subscription_state(current_user)
    now = datetime.now(timezone.utc)
    created_at = current_user.created_at
    created = (
        created_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None
        else created_at
    )

    trial_end = _safe_getattr(current_user, 'trial_ends_at', None)
    if trial_end is not None:
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        days_remaining = max(0, (trial_end - now).days)
        trial_days = max(1, (trial_end - created).days)
        days_used = max(0, min((now - created).days, trial_days))
    else:
        # Marketing window when no Stripe trial date is stored yet (informational only).
        trial_days = 60
        days_used = max(0, (now - created).days)
        days_remaining = max(0, trial_days - days_used)

    trial_percent = min(100.0, (days_used / trial_days) * 100) if trial_days else 0.0

    if trial_end is not None:
        trial_calendar_end = trial_end
    else:
        trial_calendar_end = created + timedelta(days=60)

    return render_template('monetization/trial_info.html',
                         trial_days=trial_days,
                         days_used=days_used,
                         days_remaining=days_remaining,
                         trial_percent=trial_percent,
                         trial_expired=days_remaining == 0,
                         subscription_state=state,
                         trial_calendar_end=trial_calendar_end)



@bp.route('/webhook', methods=['POST'])
@csrf.exempt
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
        current_app.logger.warning("Stripe webhook signature verification failed: %s", e)
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
                            pro_price = current_app.config.get('STRIPE_PRICE_PRO') or os.environ.get('STRIPE_PRICE_PRO')
                            pro_plus_price = current_app.config.get('STRIPE_PRICE_PRO_PLUS') or os.environ.get('STRIPE_PRICE_PRO_PLUS')
                            elite_price = current_app.config.get('STRIPE_PRICE_ELITE') or os.environ.get('STRIPE_PRICE_ELITE')
                            if price_id and price_id == pro_price:
                                plan_tier = 'pro'
                            elif price_id and price_id == pro_plus_price:
                                plan_tier = 'pro_plus'
                            elif price_id and price_id == elite_price:
                                plan_tier = 'elite'
                    except Exception as e:
                        current_app.logger.warning("Webhook subscription fetch failed: %s", e)

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
        current_app.logger.exception("Stripe webhook handling error: %s", e)
        # 500 so Stripe retries (webhook must be reliable)
        return jsonify({'ok': False}), 500

    return jsonify({'received': True})
