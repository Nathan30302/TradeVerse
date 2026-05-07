"""
Authentication Routes
User registration, login, logout, and profile management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from datetime import datetime, timedelta, timezone
import re
from flask_mail import Message
from app import mail
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, InternalError

# Create Blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')

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
        
        # If there are errors, show them
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html')
        
        # Create new user
        try:
            now = datetime.now(timezone.utc)
            new_user = User(
                username=username,
                email=email,
                full_name=full_name if full_name else None,
                created_at=now,
                # 2-month trial for all new users (Pro features during trial)
                subscription_tier='pro',
                subscription_status='trialing',
                trial_ends_at=now + timedelta(days=60),
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()

            # Welcome email (best-effort)
            try:
                from flask import current_app
                sender = current_app.config.get("MAIL_DEFAULT_SENDER")
                if sender and new_user.email:
                    msg = Message(
                        subject="Welcome to TradeVerse",
                        sender=sender,
                        recipients=[new_user.email],
                    )
                    msg.body = (
                        f"Hi {new_user.username},\n\n"
                        "Welcome to TradeVerse! Your 2-month Pro trial is active.\n\n"
                        "Log your first trade and start improving your consistency.\n"
                    )
                    mail.send(msg)
            except Exception:
                pass
            
            flash(f'🎉 Welcome to TradeVerse, {username}! Your account has been created successfully.', 'success')
            flash('📊 You can now log in and start tracking your trades!', 'info')
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash('❌ An error occurred during registration. Please try again.', 'danger')
            current_app.logger.exception("Registration error")
    
    return render_template('auth/register.html')

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
        
        # Find user
        user = None
        try:
            user = User.query.filter_by(username=username).first()
        except (OperationalError, ProgrammingError):
            # Backward-compatible auth path for partially-migrated DBs where ORM
            # selects columns that don't exist yet (would otherwise 500).
            current_app.logger.warning("Login ORM query failed (likely schema drift); attempting compat SQL fallback")
            # The ORM error may have left the transaction in an aborted state on Postgres.
            # Roll back before attempting any further SQL in this request.
            try:
                db.session.rollback()
            except Exception:
                pass
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
            # Handle "current transaction is aborted" edge case.
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
        preferred_currency = request.form.get('preferred_currency', 'USD')
        theme = request.form.get('theme', 'light')
        
        # Update profile
        try:
            current_user.full_name = full_name if full_name else None
            current_user.bio = bio if bio else None
            current_user.timezone = timezone
            current_user.preferred_currency = preferred_currency
            current_user.theme = theme
            
            db.session.commit()
            flash('✅ Profile updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('❌ Error updating profile. Please try again.', 'danger')
            current_app.logger.exception("Profile update error")
        
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html')

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
    AJAX endpoint to persist user's theme preference
    Expects JSON: { "theme": "light|dark|blue" }
    """
    try:
        data = request.get_json(force=True)
        theme = (data.get('theme') or 'light').strip().lower()
        if theme not in ('light','dark','blue'):
            return {'ok': False, 'error': 'invalid_theme'}, 400
        current_user.theme = theme
        db.session.commit()
        return {'ok': True, 'theme': theme}
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("set_theme error")
        return {'ok': False, 'error': 'server_error'}, 500