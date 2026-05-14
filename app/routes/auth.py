"""
Authentication Routes
User registration, login, logout, and profile management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from datetime import datetime, timedelta, timezone
import os
import re
import uuid
from flask_mail import Message
from app import mail
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, InternalError, IntegrityError
from sqlalchemy.orm import load_only

# Create Blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')


_PHONE_CHARS = re.compile(r"^\+?[0-9()\s.\-]{8,32}$")


def _signup_country_codes() -> set:
    ch = current_app.config.get("REGISTER_COUNTRY_CHOICES") or ()
    return {str(c[0]).strip().upper() for c in ch if c and len(c) > 0}


def _parse_signup_country(raw: str) -> tuple:
    """Return (code_or_None, error_message_or_None)."""
    c = (raw or "").strip().upper()
    if not c:
        return None, None
    if c not in _signup_country_codes():
        return None, "Invalid country selection."
    return c, None


def _parse_signup_phone(raw: str) -> tuple:
    """Return (stored_value_or_None, error_message_or_None)."""
    s = (raw or "").strip()
    if not s:
        return None, None
    if not _PHONE_CHARS.match(s):
        return None, "Phone number may only include digits, spaces, and + ( ) . - (8–32 characters)."
    compact = re.sub(r"[\s().\-]", "", s)
    if len(compact) < 8 or len(compact) > 22:
        return None, "Phone number should be 8–22 digits."
    if not re.match(r"^\+?\d+$", compact):
        return None, "Phone number format is invalid."
    return compact[:32], None


def _safe_trial_days_pro_plus() -> int:
    """Parse TV_TRIAL_DAYS_PRO_PLUS; invalid values must not break registration."""
    default = 60
    raw = os.environ.get('TV_TRIAL_DAYS_PRO_PLUS')
    if raw is None or str(raw).strip() == '':
        return default
    try:
        n = int(raw)
        return max(1, min(n, 3650))
    except (TypeError, ValueError):
        current_app.logger.warning(
            'Invalid TV_TRIAL_DAYS_PRO_PLUS=%r; using default %s',
            raw,
            default,
        )
        return default


# ==================== Registration ====================

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    User Registration
    
    Handles new user account creation with validation
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        country_raw = (request.form.get('country_code') or '').strip()
        phone_raw = (request.form.get('phone_number') or '').strip()

        # Validation
        errors = []
        
        # Username validation
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        elif len(username) > 80:
            errors.append('Username must be less than 80 characters.')
        elif not re.match(r'^[a-zA-Z0-9_-]+$', username):
            errors.append('Username can only contain letters, numbers, underscores, and hyphens.')
        
        # Email validation
        if not email:
            errors.append('Email is required.')
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append('Please provide a valid email address.')
        
        # Password validation
        if not password:
            errors.append('Password is required.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters long.')
        elif password != confirm_password:
            errors.append('Passwords do not match.')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken. Please choose another.')
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered. Please log in or use another email.')

        country_code, cerr = _parse_signup_country(country_raw)
        if cerr:
            errors.append(cerr)
        phone_number, perr = _parse_signup_phone(phone_raw)
        if perr:
            errors.append(perr)
        
        # If there are errors, show one clear message (avoid stacked flashes).
        if errors:
            if len(errors) == 1:
                flash(errors[0], 'danger')
            else:
                flash(
                    'Please fix the following before signing up: ' + '; '.join(errors),
                    'danger',
                )
            utm_keep = (
                (request.form.get('signup_utm_source') or request.args.get('utm_source') or "").strip()
            )[:255]
            return render_template("auth/register.html", signup_utm_default=utm_keep)
        
        # Create new user
        try:
            now = datetime.now(timezone.utc)
            trial_days = _safe_trial_days_pro_plus()
            utm_src = (request.form.get('signup_utm_source') or '').strip()[:255]
            new_user = User(
                username=username,
                email=email,
                full_name=full_name if full_name else None,
                created_at=now,
                # Pro Plus tier during trial (aligned with pricing page / TV_TRIAL_DAYS_PRO_PLUS)
                subscription_tier='pro_plus',
                subscription_status='trialing',
                trial_ends_at=now + timedelta(days=trial_days),
            )
            if utm_src:
                try:
                    new_user.signup_utm_source = utm_src
                except Exception:
                    pass
            try:
                new_user.country_code = country_code
                new_user.phone_number = phone_number
            except Exception:
                pass
            new_user.set_password(password)

            db.session.add(new_user)
            db.session.commit()

            # Welcome email (best-effort)
            try:
                sender = current_app.config.get("MAIL_DEFAULT_SENDER")
                if sender and new_user.email:
                    msg = Message(
                        subject="Welcome to TradeVerse",
                        sender=sender,
                        recipients=[new_user.email],
                    )
                    msg.body = (
                        f"Hi {new_user.username},\n\n"
                        "Welcome to TradeVerse! Your 2-month Pro Plus trial is active.\n\n"
                        "Log your first trade and start improving your consistency.\n"
                    )
                    mail.send(msg)
            except Exception:
                pass

            login_user(new_user, remember=False)
            flash(
                f'🎉 Welcome to TradeVerse, {username}! Your account is ready — you are signed in.',
                'success',
            )
            return redirect(url_for('dashboard.index'))

        except IntegrityError:
            db.session.rollback()
            flash(
                'That username or email is already registered. Try signing in or use different details.',
                'danger',
            )
            utm_keep = (
                (request.form.get('signup_utm_source') or request.args.get('utm_source') or '').strip()
            )[:255]
            return render_template("auth/register.html", signup_utm_default=utm_keep)

        except Exception:
            db.session.rollback()
            flash('❌ An error occurred during registration. Please try again.', 'danger')
            current_app.logger.exception("Registration error")
    
    utm_default = (
        (request.args.get("utm_source") or request.args.get("utm_campaign") or "").strip()
    )[:255]
    return render_template("auth/register.html", signup_utm_default=utm_default)

# ==================== Login ====================

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User Login
    
    Authenticates user and creates session
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            remember = request.form.get('remember', False)
        except Exception:
            current_app.logger.exception("Login request parsing failed")
            flash('❌ Login failed. Please try again.', 'danger')
            return render_template('auth/login.html')
        
        # Find user (tolerate production schema drift; avoid 500s on missing columns)
        user = None
        try:
            user = User.query.filter_by(username=username).first()
        except (OperationalError, ProgrammingError):
            current_app.logger.warning("Login ORM query failed (likely schema drift); using compat fallback")
            try:
                db.session.rollback()
            except Exception:
                pass

            # Prefer a session-bound ORM instance with safe columns only
            try:
                user = (
                    db.session.query(User)
                    .options(
                        load_only(
                            User.id,
                            User.username,
                            User.email,
                            User.password_hash,
                            User.is_active,
                            User.is_verified,
                            User.is_premium,
                            User.timezone,
                            User.preferred_currency,
                            User.theme,
                        )
                    )
                    .filter(User.username == username)
                    .first()
                )
            except Exception:
                user = None

            # Last resort: minimal raw SQL mapping
            if not user:
                row = db.session.execute(
                    text(
                        "SELECT id, username, email, password_hash, is_active, is_verified, is_premium, "
                        "timezone, preferred_currency, theme "
                        "FROM users WHERE username = :u LIMIT 1"
                    ),
                    {"u": username},
                ).mappings().first()
                if row:
                    u = User()
                    for k, v in row.items():
                        setattr(u, k, v)
                    user = u
        except InternalError:
            current_app.logger.exception("Login query failed due to aborted transaction; rolling back")
            try:
                db.session.rollback()
            except Exception:
                pass
        
        # Validate credentials
        if user and user.check_password(password):
            # Check if account is active
            if not user.is_active:
                flash('❌ Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html')
            
            # Log the user in
            try:
                login_user(user, remember=remember)
            except Exception:
                current_app.logger.exception("login_user failed")
                flash('❌ Login failed. Please try again.', 'danger')
                return render_template('auth/login.html')
            try:
                user.update_last_login()
            except Exception:
                # Never allow ancillary tracking to break login.
                current_app.logger.debug("update_last_login failed; continuing", exc_info=True)
            
            flash(f'👋 Welcome back, {user.username}!', 'success')
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            else:
                return redirect(url_for('dashboard.index'))
        else:
            flash('❌ Invalid username or password. Please try again.', 'danger')
    
    return render_template('auth/login.html')

# ==================== Logout ====================

@bp.route('/logout')
@login_required
def logout():
    """
    User Logout
    
    Ends user session and redirects to homepage
    """
    username = current_user.username
    logout_user()
    flash(f'👋 Goodbye, {username}! You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))

# --- Profile helpers (stats + avatar) -----------------------------------------

_AVATAR_EXTS = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp'})
_MAX_AVATAR_BYTES = 3 * 1024 * 1024


def _profile_stats_for_user(user):
    """Trading stats for profile header; never raises (avoids 500 on schema drift)."""
    try:
        return user.get_stats()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.exception('profile: get_stats failed')
        return {'win_rate': 0.0, 'total_trades': 0}


def _unlink_user_avatar_file(avatar_url):
    """Remove a previously stored avatar file from disk (best-effort)."""
    if not avatar_url or not isinstance(avatar_url, str):
        return
    s = avatar_url.strip()
    if s.startswith(('http://', 'https://')):
        return
    s = s.lstrip('/')
    rel_name = None
    if s.startswith('static/uploads/avatars/'):
        rel_name = s[len('static/uploads/avatars/') :]
    elif s.startswith('uploads/avatars/'):
        rel_name = s[len('uploads/avatars/') :]
    if not rel_name or '..' in rel_name or '/' in rel_name or '\\' in rel_name:
        return
    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
    full = os.path.join(folder, rel_name)
    if os.path.isfile(full):
        try:
            os.remove(full)
        except OSError:
            current_app.logger.debug('avatar unlink failed', exc_info=True)


def _save_avatar_for_user(user, storage):
    """
    Validate and store an avatar image under static/uploads/avatars/.

    Returns:
        tuple[str | None, str | None, str | None]: (error, static_relative_path, full_disk_path)
    """
    from werkzeug.utils import secure_filename

    if not storage or not storage.filename:
        return (None, None, None)
    raw = storage.filename
    ext = raw.rsplit('.', 1)[-1].lower() if '.' in raw else ''
    if ext not in _AVATAR_EXTS:
        return ('Please upload a PNG, JPG, GIF, or WebP image (max 3 MB).', None, None)
    try:
        storage.seek(0, os.SEEK_END)
        size = int(storage.tell() or 0)
        storage.seek(0)
    except Exception:
        size = -1
    if size > _MAX_AVATAR_BYTES or size < 1:
        return ('Image must be between 1 byte and 3 MB.', None, None)

    out_name = f'u{user.id}_{uuid.uuid4().hex[:16]}.{ext}'
    safe = secure_filename(out_name)
    if not safe or safe != out_name:
        return ('Invalid file name.', None, None)

    dest_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
    os.makedirs(dest_dir, exist_ok=True)
    full_path = os.path.join(dest_dir, safe)
    try:
        storage.save(full_path)
    except OSError as e:
        current_app.logger.warning('avatar save failed: %s', e)
        return ('Could not save the image. Please try again.', None, None)

    rel = f'uploads/avatars/{safe}'
    return (None, rel, full_path)


# ==================== Profile ====================

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """
    User Profile Management
    
    Allows user to view and edit their profile
    """
    if request.method == 'POST':
        # Get form data
        full_name = request.form.get('full_name', '').strip()
        bio = request.form.get('bio', '').strip()
        timezone = request.form.get('timezone', 'UTC')
        preferred_currency = (request.form.get('preferred_currency') or 'USD').strip().upper()
        allowed_codes = tuple(current_app.config.get('DISPLAY_CURRENCIES') or ())
        if allowed_codes and preferred_currency not in allowed_codes:
            preferred_currency = 'USD'
        country_raw = (request.form.get('country_code') or '').strip()
        phone_raw = (request.form.get('phone_number') or '').strip()
        field_msgs = []
        cerr = None
        perr = None
        if 'country_code' in request.form:
            country_code, cerr = _parse_signup_country(country_raw)
            if cerr:
                field_msgs.append(cerr)
        else:
            country_code = None
        if 'phone_number' in request.form:
            phone_number, perr = _parse_signup_phone(phone_raw)
            if perr:
                field_msgs.append(perr)
        else:
            phone_number = None
        allowed = current_app.config.get('ALLOWED_UI_THEMES') or frozenset()
        theme = (request.form.get('theme') or 'dark').strip().lower()
        if theme not in allowed:
            theme = 'dark'

        old_avatar_url = current_user.avatar_url
        uploaded_disk_path = None
        pending_avatar = ('noop', None)  # ('clear', None) | ('set', rel_path) | noop
        if request.form.get('remove_avatar'):
            pending_avatar = ('clear', None)
        else:
            avatar_storage = request.files.get('avatar')
            if avatar_storage and avatar_storage.filename:
                aerr, rel_path, full_disk = _save_avatar_for_user(current_user, avatar_storage)
                if aerr:
                    field_msgs.append(aerr)
                elif rel_path:
                    pending_avatar = ('set', rel_path)
                    uploaded_disk_path = full_disk

        def _rollback_new_avatar_file():
            if uploaded_disk_path and os.path.isfile(uploaded_disk_path):
                try:
                    os.remove(uploaded_disk_path)
                except OSError:
                    current_app.logger.debug('rollback avatar file failed', exc_info=True)

        # Update profile
        try:
            current_user.full_name = full_name if full_name else None
            current_user.bio = bio if bio else None
            current_user.timezone = timezone
            current_user.preferred_currency = preferred_currency
            current_user.theme = theme
            if 'country_code' in request.form and not cerr:
                try:
                    current_user.country_code = country_code
                except Exception:
                    pass
            if 'phone_number' in request.form and not perr:
                try:
                    current_user.phone_number = phone_number
                except Exception:
                    pass

            if pending_avatar[0] == 'clear':
                current_user.avatar_url = None
            elif pending_avatar[0] == 'set':
                current_user.avatar_url = pending_avatar[1]

            db.session.commit()
            if pending_avatar[0] in ('clear', 'set'):
                _unlink_user_avatar_file(old_avatar_url)
            if field_msgs:
                flash(
                    'Profile saved. '
                    + ' '.join(field_msgs)
                    + ' Country and phone were left unchanged.',
                    'warning',
                )
            else:
                flash('✅ Profile updated successfully!', 'success')

        except IntegrityError as e:
            db.session.rollback()
            _rollback_new_avatar_file()
            flash('Could not save profile due to a data conflict. Please try again.', 'danger')
            current_app.logger.warning('Profile update IntegrityError: %s', e)
        except (OperationalError, ProgrammingError, InternalError):
            db.session.rollback()
            _rollback_new_avatar_file()
            flash('Could not save profile (database error). Please try again or contact support.', 'danger')
            current_app.logger.exception('Profile update database error')
        except Exception:
            db.session.rollback()
            _rollback_new_avatar_file()
            flash('❌ Error updating profile. Please try again.', 'danger')
            current_app.logger.exception('Profile update error')

        after = (request.form.get('after_save') or '').strip().lower()
        if after == 'settings':
            return redirect(url_for('auth.settings'))
        return redirect(url_for('auth.profile'))
    
    return render_template(
        'auth/profile.html',
        profile_stats=_profile_stats_for_user(current_user),
    )

# ==================== Change Password ====================

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Change Password
    
    Allows user to change their password
    """
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not current_user.check_password(current_password):
            flash('❌ Current password is incorrect.', 'danger')
        elif len(new_password) < 8:
            flash('❌ New password must be at least 8 characters long.', 'danger')
        elif new_password != confirm_password:
            flash('❌ New passwords do not match.', 'danger')
        else:
            try:
                current_user.set_password(new_password)
                db.session.commit()
                flash('✅ Password changed successfully!', 'success')
                return redirect(url_for('auth.profile'))
            except Exception as e:
                db.session.rollback()
                flash('❌ Error changing password. Please try again.', 'danger')
                current_app.logger.exception("Password change error")
    
    return render_template('auth/change_password.html')

# ==================== Account Settings ====================

@bp.route('/settings')
@login_required
def settings():
    """
    Account Settings
    
    Advanced account configuration
    """
    # Render the consolidated account settings page
    return render_template('auth/account_settings.html')


def _purge_user_data(user_id: int) -> None:
    """Delete all application data for a user (foreign-key-safe order)."""
    from app.models.trade import Trade
    from app.models.trade_plan import TradePlan
    from app.models.trade_feedback import TradeFeedback
    from app.models.cooldown import Cooldown
    from app.models.performance_score import PerformanceScore
    from app.models.broker import UserBrokerCredential, ImportedTradeSource
    from sqlalchemy import or_

    trade_ids = [row[0] for row in db.session.query(Trade.id).filter_by(user_id=user_id).all()]
    if trade_ids:
        TradeFeedback.query.filter(
            or_(TradeFeedback.user_id == user_id, TradeFeedback.trade_id.in_(trade_ids))
        ).delete(synchronize_session=False)
    else:
        TradeFeedback.query.filter_by(user_id=user_id).delete(synchronize_session=False)

    TradePlan.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Cooldown.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    PerformanceScore.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ImportedTradeSource.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    UserBrokerCredential.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Trade.query.filter_by(user_id=user_id).delete(synchronize_session=False)

    user = db.session.get(User, user_id)
    if user:
        db.session.delete(user)
    db.session.commit()


@bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Permanently delete the signed-in account and all journal data."""
    confirm = (request.form.get('confirm_delete') or '').strip().upper()
    password = (request.form.get('password') or '').strip()
    if confirm != 'DELETE':
        flash('Type DELETE in the confirmation field to remove your account.', 'danger')
        return redirect(url_for('auth.settings'))
    if not password:
        flash('Enter your current password to confirm.', 'danger')
        return redirect(url_for('auth.settings'))
    if not current_user.check_password(password):
        flash('Password is incorrect.', 'danger')
        return redirect(url_for('auth.settings'))

    uid = current_user.id
    try:
        _purge_user_data(uid)
        logout_user()
        flash('Your account and data have been permanently deleted.', 'info')
        return redirect(url_for('main.index'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('delete_account failed')
        flash('Could not delete your account. Please try again or contact support.', 'danger')
        return redirect(url_for('auth.settings'))


@bp.route('/login-history')
@login_required
def login_history():
    """
    Login History

    Simple view showing recent login activity. Currently displays last login timestamp
    and a friendly note. This can be extended to a full audit trail later.
    """
    last_login = current_user.last_login
    # Placeholder: in future, query a LoginHistory model if available
    return render_template('auth/login_history.html', last_login=last_login)

@bp.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    """
    AJAX endpoint to persist the user's theme preference.
    Expects JSON: { "theme": "light|dark|blue|midnight|sand" } (see Config.ALLOWED_UI_THEMES).
    """
    try:
        data = request.get_json(force=True)
        allowed = current_app.config.get('ALLOWED_UI_THEMES') or frozenset()
        theme = (data.get('theme') or 'dark').strip().lower()
        if theme not in allowed:
            return jsonify(ok=False, error='invalid_theme'), 400
        current_user.theme = theme
        db.session.commit()
        return jsonify(ok=True, theme=theme)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("set_theme error")
        return jsonify(ok=False, error='server_error'), 500