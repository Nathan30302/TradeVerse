"""
Authentication Routes
User registration, login, logout, and profile management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from datetime import datetime, timedelta, timezone
import io
import os
import re
import uuid
from flask_mail import Message
from app import mail
from sqlalchemy.exc import (
    DataError,
    InternalError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.orm import load_only
from app.services.entitlements import _safe_getattr as _safe_user_col

# Create Blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')


_PHONE_CHARS = re.compile(r"^\+?[0-9()\s.\-]{8,32}$")


def _signup_country_codes() -> set:
    ch = current_app.config.get("REGISTER_COUNTRY_CHOICES") or ()
    return {
        str(c[0]).strip().upper()
        for c in ch
        if c and len(c) > 0 and str(c[0]).strip()
    }


def _parse_signup_country(raw: str, *, required: bool = False) -> tuple:
    """Return (code_or_None, error_message_or_None)."""
    c = (raw or "").strip().upper()
    if not c:
        if required:
            return None, "Please select your country."
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


def _normalize_display_name(name: str | None) -> str:
    """Lowercase single-spaced form for duplicate-name checks."""
    return ' '.join((name or '').strip().lower().split())


def _count_accounts_matching_display_name(norm: str) -> int:
    """How many users share this normalized display name (full_name)."""
    if not norm:
        return 0
    rows = db.session.query(User.full_name).filter(User.full_name.isnot(None)).all()
    return sum(1 for (fn,) in rows if _normalize_display_name(fn) == norm)


def _password_policy_errors(password: str) -> list:
    """Return human-readable password requirement violations (empty if OK)."""
    errs = []
    if not password:
        errs.append('Password is required.')
        return errs
    if len(password) < 10:
        errs.append('Password must be at least 10 characters.')
    if not re.search(r'[A-Z]', password):
        errs.append('Use at least one uppercase letter (A–Z).')
    if not re.search(r'[a-z]', password):
        errs.append('Use at least one lowercase letter (a–z).')
    if not re.search(r'[0-9]', password):
        errs.append('Use at least one number (0–9).')
    if not re.search(r'[^A-Za-z0-9]', password):
        errs.append('Use at least one symbol (for example ! @ # $ % ^ & *).')
    return errs


def _record_login_event(user_id: int) -> None:
    """Append a login audit row (best-effort; never raises)."""
    try:
        from app.models.user_login_event import UserLoginEvent

        raw_ip = request.headers.get('X-Forwarded-For') or request.remote_addr or ''
        ip = (raw_ip.split(',')[0].strip() if raw_ip else '')[:45] or None
        ua = (request.headers.get('User-Agent') or '')[:512] or None
        db.session.add(UserLoginEvent(user_id=user_id, ip_address=ip, user_agent=ua))
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.debug('login event recording skipped', exc_info=True)


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
        
        # Full name (required; used for duplicate-person cap)
        if not full_name or len(full_name.strip()) < 2:
            errors.append('Full name is required (at least 2 characters). Use the same name you use in real life.')

        # Password validation
        if not password:
            errors.append('Password is required.')
        elif password != confirm_password:
            errors.append('Passwords do not match.')
        else:
            errors.extend(_password_policy_errors(password))

        max_accounts = int(current_app.config.get('MAX_ACCOUNTS_PER_DISPLAY_NAME', 2) or 2)
        norm_name = _normalize_display_name(full_name)
        if norm_name and _count_accounts_matching_display_name(norm_name) >= max_accounts:
            errors.append(
                f'At most {max_accounts} TradeVerse accounts may use this full name. '
                'Contact support if you need an exception.'
            )

        if User.query.filter_by(username=username).first():
            errors.append('Username already taken. Please choose another.')
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered. Please log in or use another email.')

        country_code, cerr = _parse_signup_country(country_raw, required=True)
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
            try:
                new_user.update_last_login()
            except Exception:
                current_app.logger.debug('new user last_login skipped', exc_info=True)
            _record_login_event(new_user.id)
            flash(
                f'🎉 Welcome to TradeVerse, {username}! Your account is ready — you are signed in.',
                'success',
            )
            return redirect(url_for('dashboard.getting_started'))

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
            remember = request.form.get('remember') in ('1', 'on', 'true', 'yes')
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

            # Last resort: raw SQL hydration (wide row when possible)
            if not user:
                from app.services.user_db_compat import hydrate_user_from_db

                user = hydrate_user_from_db(db.session, User, username=username)
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
            _record_login_event(user.id)

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
_MAX_BIO_CHARS = 100_000  # TEXT column; cap avoids pathological payloads


def _strip_nulls(s: str) -> str:
    """PostgreSQL rejects NUL in text/varchar; strip defensively."""
    if not s or '\x00' not in s:
        return s
    return s.replace('\x00', '')


def _clip_profile_str(s: str | None, max_len: int) -> str | None:
    """Normalize optional profile text to DB-safe length (no NUL)."""
    if s is None:
        return None
    t = _strip_nulls(str(s).strip())
    if not t:
        return None
    if len(t) <= max_len:
        return t
    return t[:max_len]


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
    from app.services.uploads_storage import resolve_avatar_file

    found = resolve_avatar_file(rel_name)
    if not found:
        return
    folder, name = found
    full = os.path.join(folder, name)
    try:
        os.remove(full)
    except OSError:
        current_app.logger.debug('avatar unlink failed', exc_info=True)


def _read_avatar_upload_bytes(storage) -> tuple[bytes | None, str | None]:
    """
    Read upload body with a hard 3 MB cap.

    ``content_length`` and ``seek``/``tell`` are unreliable on multipart streams
    (often 0 or wrong), which falsely failed the old size check. Size is always
    determined by reading the stream.
    """
    try:
        storage.seek(0)
    except Exception:
        pass
    stream = getattr(storage, 'stream', None) or storage
    buf = io.BytesIO()
    chunk_sz = 256 * 1024
    total = 0
    try:
        while True:
            piece = stream.read(chunk_sz)
            if not piece:
                break
            total += len(piece)
            if total > _MAX_AVATAR_BYTES:
                return None, 'That photo is larger than 3 MB. Compress it or pick a smaller image.'
            buf.write(piece)
    except OSError as e:
        current_app.logger.warning('avatar read failed: %s', e)
        return None, 'Could not read that file. Try another photo (PNG, JPG, GIF, or WebP).'

    data = buf.getvalue()
    if len(data) < 1:
        return None, 'That file looks empty. Try another photo or export as JPEG/PNG.'
    return data, None


def _save_avatar_for_user(user, storage):
    """
    Validate and store an avatar under a writable avatars directory.

    Also mirrors a copy into ``static/uploads/avatars`` when that path differs,
    so the photo still serves if the primary durable disk is unavailable later.

    Returns:
        tuple[str | None, str | None, str | None]: (error, relative_path, full_disk_path)
    """
    from werkzeug.utils import secure_filename
    from app.services.uploads_storage import avatars_dir, static_avatars_mirror_dir, resolve_avatar_file

    if not storage or not storage.filename:
        return (None, None, None)
    raw = storage.filename
    ext = raw.rsplit('.', 1)[-1].lower() if '.' in raw else ''
    if ext not in _AVATAR_EXTS:
        return ('Use a PNG, JPG, GIF, or WebP file (max 3 MB).', None, None)

    data, read_err = _read_avatar_upload_bytes(storage)
    if read_err:
        return (read_err, None, None)

    out_name = f'u{user.id}_{uuid.uuid4().hex[:16]}.{ext}'
    safe = secure_filename(out_name)
    if not safe or safe != out_name:
        return ('Invalid file name.', None, None)

    dest_dir = avatars_dir()
    full_path = os.path.join(dest_dir, safe)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(full_path, 'wb') as out_f:
            out_f.write(data)
    except OSError as e:
        current_app.logger.warning('avatar save failed: %s', e)
        return ('Could not save the image. Please try again.', None, None)

    # Mirror into static tree when primary is elsewhere (e.g. /var/data).
    mirror = static_avatars_mirror_dir()
    if mirror and os.path.abspath(mirror) != os.path.abspath(dest_dir):
        try:
            mirror_path = os.path.join(mirror, safe)
            with open(mirror_path, 'wb') as out_f:
                out_f.write(data)
        except OSError:
            current_app.logger.debug('avatar static mirror skipped', exc_info=True)

    if not resolve_avatar_file(safe):
        current_app.logger.warning('avatar saved but not resolvable: %s', full_path)
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
        except OSError:
            pass
        return ('Photo was written but could not be verified. Please try again.', None, None)

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
        # Get form data (clip + strip NUL so VARCHAR/TEXT never trips DB DataError)
        full_name = _clip_profile_str(request.form.get('full_name'), 100)
        bio = _clip_profile_str(request.form.get('bio'), _MAX_BIO_CHARS)
        timezone = (_strip_nulls((request.form.get('timezone') or 'UTC').strip()) or 'UTC')[:50]
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
        allowed_fonts = current_app.config.get('ALLOWED_UI_FONTS') or frozenset()
        ui_font = (request.form.get('ui_font') or 'jakarta').strip().lower()
        if ui_font not in allowed_fonts:
            ui_font = 'jakarta'

        # Always mutate a session-bound User. Flask-Login may hand us a detached
        # schema-compat hydrate; assigning on that object and commit() is a no-op
        # (file written, avatar_url never persisted) — the profile photo bug.
        from app.models.user import User as UserModel

        user = db.session.get(UserModel, current_user.id)
        if user is None:
            flash('Could not load your account to save. Please sign in again.', 'danger')
            after = (request.form.get('after_save') or '').strip().lower()
            if after == 'settings':
                return redirect(url_for('auth.settings'))
            return redirect(url_for('auth.profile'))

        old_avatar_url = user.avatar_url
        uploaded_disk_path = None
        pending_avatar = ('noop', None)  # ('clear', None) | ('set', rel_path) | noop
        # Prefer a new upload over "remove" if both are submitted.
        avatar_storage = request.files.get('avatar')
        if avatar_storage and avatar_storage.filename:
            aerr, rel_path, full_disk = _save_avatar_for_user(user, avatar_storage)
            if aerr:
                field_msgs.append(aerr)
            elif rel_path:
                pending_avatar = ('set', rel_path)
                uploaded_disk_path = full_disk
        elif request.form.get('remove_avatar'):
            pending_avatar = ('clear', None)

        def _rollback_new_avatar_file():
            if uploaded_disk_path and os.path.isfile(uploaded_disk_path):
                try:
                    os.remove(uploaded_disk_path)
                except OSError:
                    current_app.logger.debug('rollback avatar file failed', exc_info=True)

        # Update profile
        try:
            user.full_name = full_name if full_name else None
            user.bio = bio if bio else None
            user.timezone = timezone
            user.preferred_currency = preferred_currency
            user.theme = theme
            try:
                user.ui_font = ui_font
            except Exception:
                pass
            if 'country_code' in request.form and not cerr:
                try:
                    user.country_code = country_code
                except Exception:
                    pass
            if 'phone_number' in request.form and not perr:
                try:
                    user.phone_number = phone_number
                except Exception:
                    pass

            if pending_avatar[0] == 'clear':
                user.avatar_url = None
            elif pending_avatar[0] == 'set':
                user.avatar_url = pending_avatar[1]

            db.session.commit()
            if pending_avatar[0] in ('clear', 'set'):
                _unlink_user_avatar_file(old_avatar_url)
            if pending_avatar[0] == 'set':
                flash('✅ Profile photo saved.', 'success')
            elif field_msgs:
                flash('✅ Profile saved. ' + ' '.join(field_msgs), 'warning')
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
        except DataError:
            db.session.rollback()
            _rollback_new_avatar_file()
            flash(
                'Could not save profile: one field was too long or contained invalid characters. '
                'Try a shorter name or bio.',
                'danger',
            )
            current_app.logger.warning('Profile update DataError', exc_info=True)
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
        profile_country_code=(_safe_user_col(current_user, 'country_code', None) or ''),
        profile_phone_number=(_safe_user_col(current_user, 'phone_number', None) or ''),
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
        elif new_password != confirm_password:
            flash('❌ New passwords do not match.', 'danger')
        else:
            pw_errs = _password_policy_errors(new_password)
            if pw_errs:
                flash(
                    'New password does not meet security rules: ' + ' '.join(pw_errs),
                    'danger',
                )
            else:
                try:
                    current_user.set_password(new_password)
                    db.session.commit()
                    flash('✅ Password changed successfully!', 'success')
                    return redirect(url_for('auth.profile'))
                except Exception:
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
    return render_template(
        'auth/account_settings.html',
        profile_country_code=(_safe_user_col(current_user, 'country_code', None) or ''),
        profile_phone_number=(_safe_user_col(current_user, 'phone_number', None) or ''),
    )


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
    Login History: last successful logins and users.last_login (shown in your timezone).
    """
    from zoneinfo import ZoneInfo

    tz_name = (_safe_user_col(current_user, 'timezone', None) or 'UTC').strip()
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = 'UTC'
        user_tz = ZoneInfo('UTC')

    events = []
    try:
        from app.models.user_login_event import UserLoginEvent

        events = (
            UserLoginEvent.query.filter_by(user_id=current_user.id)
            .order_by(UserLoginEvent.occurred_at.desc())
            .limit(30)
            .all()
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.debug('login history query skipped', exc_info=True)

    last_login = _safe_user_col(current_user, 'last_login', None)

    def _to_user_tz(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(user_tz)

    last_login_local = _to_user_tz(last_login)
    event_rows = []
    for e in events:
        event_rows.append(
            {
                'at': _to_user_tz(e.occurred_at),
                'ip': e.ip_address,
                'ua': e.user_agent,
            }
        )

    return render_template(
        'auth/login_history.html',
        event_rows=event_rows,
        user_timezone_label=tz_name,
        last_login_local=last_login_local,
    )

@bp.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    """
    AJAX endpoint to persist the user's theme preference.
    Expects JSON: { "theme": "<allowed theme id>" } (see Config.ALLOWED_UI_THEMES).
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

@bp.route('/set-font', methods=['POST'])
@login_required
def set_font():
    """
    AJAX endpoint to persist the user's UI font preference.
    Expects JSON: { "font": "jakarta|manrope|sora" } (see Config.ALLOWED_UI_FONTS).
    """
    try:
        data = request.get_json(force=True)
        allowed = current_app.config.get('ALLOWED_UI_FONTS') or frozenset()
        font = (data.get('font') or 'jakarta').strip().lower()
        if font not in allowed:
            return jsonify(ok=False, error='invalid_font'), 400
        try:
            current_user.ui_font = font
        except Exception:
            return jsonify(ok=False, error='font_unavailable'), 503
        db.session.commit()
        return jsonify(ok=True, font=font)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("set_font error")
        return jsonify(ok=False, error='server_error'), 500
