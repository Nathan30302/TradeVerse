"""
TradeVerse Application Factory
Professional Flask application initialization using the Factory Pattern
"""

from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import config
import os

# Initialize Flask extensions (will be bound to app in create_app)
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()

def create_app(config_name='default'):
    """
    Application Factory Pattern
    """
    
    # Create Flask app instance
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Trust proxy headers in hosted environments (Render / Nginx).
    # This prevents generating http:// canonical/sitemap URLs behind HTTPS.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Production hardening: require env-managed secrets (no fallbacks).
    if config_name == 'production':
        if not app.config.get('SECRET_KEY'):
            raise RuntimeError("SECRET_KEY must be set in production.")
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError("DATABASE_URL must be set in production.")

    # Ensure instance folder exists (skip on read-only filesystems)
    try:
        os.makedirs(app.instance_path)
    except (OSError, PermissionError):
        pass

    # Ensure upload folder exists
    upload_folder = app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        try:
            os.makedirs(upload_folder, exist_ok=True)
            for key in ('AVATARS_FOLDER', 'TRADE_SCREENSHOTS_FOLDER', 'REPLAY_UPLOADS_FOLDER', 'PLAYBOOK_IMAGES_FOLDER'):
                path = app.config.get(key)
                if path:
                    os.makedirs(path, exist_ok=True)
        except (OSError, PermissionError):
            pass
    try:
        from app.services.uploads_storage import ensure_upload_dirs

        ensure_upload_dirs()
    except Exception:
        pass

    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    from app.orm_hooks import install_once as _install_tradeverse_orm_hooks

    _install_tradeverse_orm_hooks()
    mail.init_app(app)
    csrf.init_app(app)
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '🔒 Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Import models (inside app context to avoid circular imports)
    with app.app_context():
        from app import schema_compat

        schema_compat.refresh(app)
        # Idempotent: fill gaps Alembic may have skipped (safe raw SQL).
        schema_compat.ensure_lagging_schema(app)

        from app.models import user, trade
        from app.models.user_login_event import UserLoginEvent  # noqa: F401 — register table
        from app.models.trade_plan import TradePlan
        from app.models.performance_score import PerformanceScore
        from app.models.trade_feedback import TradeFeedback
        from app.models.cooldown import Cooldown
        
        # User loader callback for Flask-Login
        @login_manager.user_loader
        def load_user(user_id):
            """
            Load the session user.

            Render/Postgres often closes idle SSL connections (``SSL SYSCALL error: EOF``).
            Retry once with a fresh session before falling back to the schema-compat hydrate.
            """
            from sqlalchemy.exc import OperationalError, DisconnectionError

            uid = int(user_id)
            last_exc = None
            for attempt in range(2):
                try:
                    u = db.session.get(user.User, uid)
                    if u is not None:
                        from app.services.user_db_compat import stamp_omitted_user_columns

                        stamp_omitted_user_columns(u)
                    return u
                except (OperationalError, DisconnectionError) as exc:
                    last_exc = exc
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    try:
                        db.session.remove()
                    except Exception:
                        pass
                    if attempt == 0:
                        app.logger.warning(
                            "load_user: DB connection dropped (attempt %s); retrying",
                            attempt + 1,
                        )
                        continue
                    app.logger.warning(
                        "load_user ORM failed after retry (likely dead connection); using compat fallback",
                        exc_info=True,
                    )
                except Exception as exc:
                    last_exc = exc
                    app.logger.warning(
                        "load_user ORM failed (likely schema drift); using compat fallback",
                        exc_info=True,
                    )
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    break

            try:
                from app.models.user import User as UserModel
                from app.services.user_db_compat import hydrate_user_from_db

                hydrated = hydrate_user_from_db(db.session, UserModel, user_id=uid)
                if hydrated is None:
                    return None
                # Prefer a session-bound instance so profile / settings commits persist.
                try:
                    managed = db.session.get(UserModel, uid)
                    if managed is not None:
                        from app.services.user_db_compat import stamp_omitted_user_columns

                        stamp_omitted_user_columns(managed)
                        return managed
                except Exception:
                    pass
                return hydrated
            except Exception:
                app.logger.exception("load_user compat fallback failed (prior=%r)", last_exc)
                return None

        # Seed instruments from EXNESS catalog on startup (dev/test only).
        # Schema is managed by Alembic migrations; if the DB hasn't been upgraded yet,
        # skip seeding rather than mutating schema at runtime.
        if config_name != 'production' and os.environ.get('SEED_INSTRUMENTS', '1') == '1':
            try:
                _seed_instruments(app)
            except Exception as e:
                app.logger.debug(f"Instrument seeding skipped (DB not ready?): {e}")
    
    # Register blueprints (routes)
    from app.routes import auth, main, trade as trade_routes, dashboard
    from app.routes import planner, instruments
    from app.routes import playbook
    from app.routes import replay

    tv_schema = app.extensions.get("tradeverse_schema") or {}
    
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(trade_routes.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(planner.bp)
    app.register_blueprint(instruments.bp)
    # Register unconditionally (like replay) so routes never 404 when migrations lag.
    app.register_blueprint(playbook.bp)
    app.register_blueprint(replay.bp)

    from app.routes import lab
    app.register_blueprint(lab.bp)

    # Register admin blueprint
    from app.routes import admin
    app.register_blueprint(admin.bp)

    # Register monetization blueprint
    from app.routes import monetization
    app.register_blueprint(monetization.bp)

    # Broker & import APIs
    from app.routes import brokers as brokers_routes, imports as imports_routes
    from app.routes import api_instruments
    app.register_blueprint(brokers_routes.bp)
    app.register_blueprint(imports_routes.bp)
    app.register_blueprint(api_instruments.bp)

    from app.routes import api_voice
    app.register_blueprint(api_voice.bp)

    # Owner admin dashboard (RBAC)
    from app.routes import owner_admin
    app.register_blueprint(owner_admin.bp)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register CLI commands
    from app import commands
    try:
        commands.register_commands(app)
    except Exception:
        app.logger.debug('Failed to register CLI commands')
    
    # Build FTS index on first request (delayed startup)
    @app.before_request
    def _build_fts_once():
        if not app.config.get('ENABLE_FTS_BUILD', True):
            return
        if not hasattr(app, '_fts_built'):
            try:
                from app.models.instrument_fts import build_fts_index
                build_fts_index()
                app._fts_built = True
            except Exception as e:
                app.logger.debug(f"FTS index build skipped: {e}")
                app._fts_built = True

    # Prometheus /metrics — off by default (enable explicitly; protect scrapers at the edge).
    if app.config.get('PROMETHEUS_METRICS_ENABLED'):
        try:
            from prometheus_client import make_wsgi_app  # type: ignore
            from werkzeug.middleware.dispatcher import DispatcherMiddleware
            app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
                '/metrics': make_wsgi_app()
            })
        except (ImportError, Exception):
            app.logger.debug('prometheus_client not available; /metrics disabled')

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # Allow mic on this origin for trade voice notes (Web Speech API / MediaRecorder).
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(self), geolocation=()',
        )
        return response

    @app.after_request
    def _html_cache_control(response):
        """Safari aggressively caches HTML — avoid stale landing/UI after deploys."""
        ct = (response.content_type or '').lower()
        if 'text/html' in ct:
            response.headers['Cache-Control'] = 'no-cache, must-revalidate'
            response.headers.setdefault('Pragma', 'no-cache')
        return response

    @app.after_request
    def _request_id_header(response):
        from uuid import uuid4
        rid = getattr(request, '_tv_request_id', None) or uuid4().hex[:16]
        response.headers.setdefault('X-Request-ID', rid)
        return response

    @app.teardown_request
    def _rollback_failed_db_session(exc):
        """If a request ends with an error, clear an aborted Postgres transaction."""
        if exc is None:
            return
        try:
            db.session.rollback()
        except Exception:
            pass

    @app.before_request
    def _assign_request_id():
        from uuid import uuid4
        request._tv_request_id = uuid4().hex[:16]
    
    # Register template filters
    register_template_filters(app)
    
    # Register context processors
    register_context_processors(app)
    
    return app


def _seed_instruments(app):
    """
    Seed instruments from EXNESS full catalog on startup.

    FIX: Previously checked `if Instrument.query.first() is not None: return`
    which skipped reseeding when the old 17-stub instruments were present.
    Now checks the actual count — if fewer than 200 instruments exist,
    it reseeds with the full DEFAULT_INSTRUMENTS catalog (257 instruments).
    """
    import json
    from app.models.instrument import Instrument, DEFAULT_INSTRUMENTS

    current_count = Instrument.query.count()

    # If we already have a full catalog, skip seeding
    if current_count >= 200:
        app.logger.info(f"Instruments already seeded: {current_count} instruments found.")
        return

    # If partial/stub data exists, clear it first
    if current_count > 0:
        app.logger.info(f"Found only {current_count} instruments (stub data). Clearing and reseeding...")
        try:
            db.session.execute(db.text('DELETE FROM instrument_aliases'))
            db.session.execute(db.text('DELETE FROM instruments'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Failed to clear stub instruments: {e}")
            return

    # Try to load from catalog JSON file first
    seed_list = DEFAULT_INSTRUMENTS
    
    # Look in the app's own directory and parent directories
    search_paths = [
        os.path.join(app.root_path, '..', 'data', 'exness_full_catalog.json'),
        os.path.join(app.root_path, '..', '..', 'data', 'exness_full_catalog.json'),
        os.path.join(app.root_path, 'data', 'exness_full_catalog.json'),
    ]
    
    for catalog_path in search_paths:
        catalog_path = os.path.normpath(catalog_path)
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    if isinstance(data, dict) and 'instruments' in data:
                        seed_list = data['instruments']
                    elif isinstance(data, list):
                        seed_list = data
                app.logger.info(f"Loaded {len(seed_list)} instruments from {catalog_path}")
                break
            except Exception as e:
                app.logger.warning(f"Failed to load catalog from {catalog_path}: {e}")

    # Deduplicate by symbol
    seen_symbols = set()
    unique_instruments = []
    for inst_data in seed_list:
        symbol = inst_data.get('symbol', '').upper()
        if symbol and symbol not in seen_symbols:
            seen_symbols.add(symbol)
            unique_instruments.append(inst_data)

    app.logger.info(f"Seeding {len(unique_instruments)} unique instruments...")

    for inst_data in unique_instruments:
        instrument = Instrument(
            symbol=inst_data.get('symbol', '').upper(),
            name=inst_data.get('name', inst_data.get('symbol', '')),
            instrument_type=inst_data.get('instrument_type', 'forex'),
            category=inst_data.get('category', 'Forex'),
            pip_size=inst_data.get('pip_size', 0.0001),
            tick_value=inst_data.get('tick_value', 1.0),
            contract_size=inst_data.get('contract_size', 100000),
            price_decimals=inst_data.get('price_decimals', 5),
            is_active=True
        )
        db.session.add(instrument)

    try:
        db.session.commit()
        final_count = Instrument.query.count()
        app.logger.info(f"Successfully seeded {final_count} instruments.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to seed instruments: {e}")


def register_error_handlers(app):
    """Register custom error handlers"""

    try:
        from flask_wtf.csrf import CSRFError
    except ImportError:  # pragma: no cover
        CSRFError = None

    if CSRFError is not None:

        @app.errorhandler(CSRFError)
        def csrf_error(error):
            """Avoid opaque 400s when POST arrives without a valid CSRF token."""
            db.session.rollback()
            return render_template('errors/csrf.html'), 400
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403


def register_template_filters(app):
    """Register custom Jinja2 template filters"""
    
    from datetime import datetime
    
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except:
                return value
        try:
            return value.strftime(format)
        except Exception:
            return ""

    @app.template_filter('currency')
    def format_currency(value, currency='USD'):
        """Format stored USD-equivalent amounts in the user's display currency."""
        from app.services.fx_display import format_converted_money

        return format_converted_money(value, currency or 'USD')
    
    @app.template_filter('percentage')
    def format_percentage(value, decimals=2):
        if value is None:
            return "0%"
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "0%"
        import math

        if not math.isfinite(v):
            return "0%"
        return f"{v:.{decimals}f}%"
    
    @app.template_filter('rr_ratio')
    def format_rr_ratio(value):
        if value is None:
            return "N/A"
        return f"1:{value:.2f}"


def register_context_processors(app):
    """Register context processors"""
    
    import random
    from flask_login import current_user
    from app.services.entitlements import user_has_feature
    from app.services.cooldown_manager import get_active_cooldown
    
    @app.context_processor
    def inject_globals():
        import json
        from datetime import datetime, timezone
        from app.content.motivational_quotes import MOTIVATIONAL_QUOTES, QUOTE_ROTATION_MS

        _mq = MOTIVATIONAL_QUOTES
        _mq_texts = [q['text'] for q in _mq] if _mq else app.config.get('QUOTES', [])

        return {
            'app_name': app.config.get('APP_NAME'),
            'app_tagline': app.config.get('APP_TAGLINE'),
            'app_version': app.config.get('APP_VERSION'),
            'random_quote': random.choice(_mq_texts) if _mq_texts else '',
            'motivational_quotes_json': json.dumps(_mq),
            'quote_rotation_ms': app.config.get('QUOTE_ROTATION_INTERVAL', QUOTE_ROTATION_MS),
            'maintenance_mode': bool(app.config.get('MAINTENANCE_MODE')),
            'support_email': app.config.get('SUPPORT_EMAIL') or 'tradeversesupport@gmail.com',
            'discord_community_url': (app.config.get('DISCORD_COMMUNITY_URL') or '').strip(),
            'ui_theme_choices': tuple(app.config.get('UI_THEME_CHOICES') or ()),
            'current_year': datetime.now(timezone.utc).year,
            'voice_transcribe_enabled': bool(os.environ.get('OPENAI_API_KEY', '').strip()),
        }

    @app.context_processor
    def inject_seo_canonical():
        from flask import request
        from app.services.seo import canonical_url_for_request, public_site_origin

        try:
            cu = canonical_url_for_request(app, request)
            origin = public_site_origin(app, request)
        except Exception:
            cu, origin = "", ""
        return {'seo_canonical_url': cu, 'seo_site_origin': origin}

    @app.context_processor
    def inject_fx_display():
        """USD→preferred multiplier for charts/JS; currency lists for settings."""
        from flask_login import current_user
        from app.services.fx_display import DISPLAY_LABELS, get_usd_rates_map, usd_to_preferred_multiplier

        codes = tuple(app.config.get('DISPLAY_CURRENCIES') or ())
        if not codes:
            codes = ('USD', 'ZAR', 'ZMW', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD')
        if not getattr(current_user, 'is_authenticated', False):
            return {
                'fx_usd_to_preferred': 1.0,
                'chart_currency_code': 'USD',
                'display_currencies': codes,
                'display_currency_labels': DISPLAY_LABELS,
            }
        cur = (getattr(current_user, 'preferred_currency', None) or 'USD').strip().upper()
        rates = get_usd_rates_map()
        # Charts: use ISO code that matches numeric scale (avoid ZAR label on USD-scale values)
        if cur != 'USD' and cur not in rates:
            chart_ccy = 'USD'
            mult = 1.0
        else:
            chart_ccy = cur
            try:
                mult = usd_to_preferred_multiplier(cur)
            except Exception:
                mult = 1.0
        return {
            'fx_usd_to_preferred': mult,
            'chart_currency_code': chart_ccy,
            'display_currencies': codes,
            'display_currency_labels': DISPLAY_LABELS,
        }

    @app.context_processor
    def inject_entitlements():
        def has_feature(feature: str) -> bool:
            if not getattr(current_user, 'is_authenticated', False):
                return False
            return user_has_feature(current_user, feature)

        return {'has_feature': has_feature}

    @app.context_processor
    def inject_trial_countdown():
        """Days left in Pro Plus trial + configured trial length (for UI copy)."""
        import os
        from app.services.entitlements import get_trial_days_remaining

        period = int(os.environ.get('TV_TRIAL_DAYS_PRO_PLUS', '60') or '60')
        if not getattr(current_user, 'is_authenticated', False):
            return {'trial_days_remaining': None, 'trial_period_days': period}
        return {
            'trial_days_remaining': get_trial_days_remaining(current_user),
            'trial_period_days': period,
        }

    @app.context_processor
    def inject_retention_today_strip():
        """Lightweight review/streak counts for the mobile today strip."""
        if not getattr(current_user, 'is_authenticated', False):
            return {}
        try:
            from app.services.retention import get_today_strip_context
            return {'today_strip': get_today_strip_context(current_user)}
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            return {'today_strip': {'reviews': 0, 'streak': 0}}

    @app.context_processor
    def inject_cooldown():
        """
        Provide active cooldown to all templates so base.html can enforce a global lock overlay.
        """
        if not getattr(current_user, 'is_authenticated', False):
            return {'global_active_cooldown': None}
        try:
            cd = get_active_cooldown(current_user.id)
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            cd = None
        return {'global_active_cooldown': cd}

    @app.context_processor
    def inject_tradeverse_optional_features():
        """Expose feature flags for Playbook/Replay in templates."""
        tv = app.extensions.get("tradeverse_schema") or {}
        # Always show Playbook in nav when the blueprint is registered (core feature).
        # Schema readiness still gates DB writes inside routes if needed.
        return {
            'feature_playbook': bool('playbook' in app.blueprints),
            'feature_replay': bool(tv.get('replay_ready') and ('replay' in app.blueprints)),
        }

    @app.context_processor
    def inject_planner_screenshot_url():
        """URLs for planner images and profile media (persistent disk or static/)."""

        def planner_screenshot_url(stored_path):
            from flask import url_for

            if not stored_path:
                return ''
            try:
                return url_for('main.planner_screenshot_file', stored=stored_path)
            except Exception:
                return ''

        def media_url(stored_path, default_static='img/default-avatar.svg'):
            from app.services.uploads_storage import media_url as _media_url

            try:
                return _media_url(stored_path, default_static=default_static)
            except Exception:
                from flask import url_for

                return url_for('static', filename=default_static)

        return {
            'planner_screenshot_url': planner_screenshot_url,
            'media_url': media_url,
        }

    @app.context_processor
    def inject_owner_platform():
        """Owner analytics: RBAC allowlist or /owner/unlock session (SECRET_KEY / OWNER_ADMIN_TOKEN)."""
        from flask import session
        from app.routes.owner_admin import SESSION_OWNER_PLATFORM
        from app.services.entitlements import _safe_getattr, is_owner_user

        if not getattr(current_user, 'is_authenticated', False):
            return {
                'owner_platform_access': False,
                'owner_platform_session_only': False,
            }

        role = (_safe_getattr(current_user, 'role', None) or 'user').strip().lower()
        rbac = role == 'owner' or is_owner_user(current_user)
        sess = bool(session.get(SESSION_OWNER_PLATFORM))

        return {
            'owner_platform_access': rbac or sess,
            'owner_platform_session_only': sess and not rbac,
        }
