"""
TradeVerse Application Factory
Professional Flask application initialization using the Factory Pattern
"""

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
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
    
    Creates and configures the Flask application with all extensions,
    blueprints, error handlers, and custom filters.
    
    Args:
        config_name: Configuration environment ('development', 'production', 'testing')
    
    Returns:
        Configured Flask application instance
    """
    
    # Create Flask app instance
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Comment out bootstrap secrets for serverless
    # Attempt to bootstrap secrets (e.g., Fernet key) from Vault/AWS at startup
    # try:
    #     from app.utils.credential_manager import bootstrap_secrets
    #     found = bootstrap_secrets()
    #     if not found and config_name == 'production':
    #         raise RuntimeError('Encryption key not found in environment or secret store (Vault/AWS)')
    # except Exception as e:
    #     # In non-production, continue but log
    #     app.logger.debug(f'Secret bootstrap: {e}')

    # Comment out instance folder creation for read-only file system
    # Ensure instance folder exists
    # try:
    #     os.makedirs(app.instance_path)
    # except OSError:
    #     pass

    # Comment out upload folder creation for read-only file system
    # Ensure upload folder exists
    # upload_folder = app.config.get('UPLOAD_FOLDER')
    # if upload_folder:
    #     os.makedirs(upload_folder, exist_ok=True)
    
    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '🔒 Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Import models (inside app context to avoid circular imports)
    with app.app_context():
        from app.models import user, trade
        from app.models.trade_plan import TradePlan
        from app.models.performance_score import PerformanceScore
        from app.models.trade_feedback import TradeFeedback
        from app.models.cooldown import Cooldown
        
        # User loader callback for Flask-Login
        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(user.User, int(user_id))
        
        # Create database tables
        db.create_all()
        
        # Auto-add missing columns for local dev (SQLite) to avoid OperationalError
        # This is a workaround for dev environments without proper migrations
        from sqlalchemy import inspect, text
        url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        is_sqlite = url and url.startswith('sqlite')
        
        if is_sqlite:
            try:
                inspector = inspect(db.engine)
                
                # Add missing trade_plans columns
                if 'trade_plans' in inspector.get_table_names():
                    tp_cols = [c['name'] for c in inspector.get_columns('trade_plans')]
                    if 'executed' not in tp_cols:
                        try:
                            db.session.execute(text('ALTER TABLE trade_plans ADD COLUMN executed BOOLEAN NOT NULL DEFAULT 0'))
                            db.session.execute(text('ALTER TABLE trade_plans ADD COLUMN executed_trade_id INTEGER'))
                            db.session.commit()
                        except Exception as e:
                            print(f"[AUTO-MIGRATE] Could not add trade_plans.executed: {e}")
                            db.session.rollback()
                
                # Add missing users subscription/billing columns
                if 'users' in inspector.get_table_names():
                    user_cols = {c['name'] for c in inspector.get_columns('users')}
                    required_cols = {
                        'subscription_tier': "VARCHAR(20) DEFAULT 'free'",
                        'subscription_status': "VARCHAR(20) DEFAULT 'active'",
                        'trial_ends_at': 'DATETIME',
                        'subscription_expires_at': 'DATETIME',
                        'stripe_customer_id': 'VARCHAR(255)'
                    }
                    
                    for col_name, col_def in required_cols.items():
                        if col_name not in user_cols:
                            try:
                                db.session.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_def}'))
                                db.session.commit()
                                print(f"[AUTO-MIGRATE] Added users.{col_name}")
                            except Exception as e:
                                print(f"[AUTO-MIGRATE] Could not add users.{col_name}: {e}")
                                db.session.rollback()
            except Exception as e:
                print(f"[AUTO-MIGRATE] Error: {e}")
                db.session.rollback()
    
    # Register blueprints (routes)
    from app.routes import auth, main, trade as trade_routes, dashboard
    from app.routes import planner, instruments
    
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(trade_routes.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(planner.bp)
    app.register_blueprint(instruments.bp)

    # Register monetization blueprint
    from app.routes import monetization
    app.register_blueprint(monetization.bp)
    # Broker & import APIs
    from app.routes import brokers as brokers_routes, imports as imports_routes
    from app.routes import api_instruments
    app.register_blueprint(brokers_routes.bp)
    app.register_blueprint(imports_routes.bp)
    app.register_blueprint(api_instruments.bp)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register CLI commands
    from app import commands
    try:
        commands.register_commands(app)
    except Exception:
        # If registration fails for any reason, continue without CLI commands
        app.logger.debug('Failed to register CLI commands')
    
    # Build FTS index on first request (delayed startup)
    @app.before_request
    def _build_fts_once():
        if not hasattr(app, '_fts_built'):
            try:
                from app.models.instrument_fts import build_fts_index
                build_fts_index()
                app._fts_built = True
            except Exception as e:
                app.logger.debug(f"FTS index build skipped: {e}")
                app._fts_built = True  # Don't retry

    # Comment out Prometheus metrics for Vercel deployment
    # Expose Prometheus metrics if prometheus_client is available
    # try:
    #     from prometheus_client import make_wsgi_app
    #     from werkzeug.middleware.dispatcher import DispatcherMiddleware
    #     # mount the prometheus WSGI app at /metrics
    #     app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    #         '/metrics': make_wsgi_app()
    #     })
    # except Exception:
    #     app.logger.debug('prometheus_client not available; /metrics disabled')
    
    # Register template filters
    register_template_filters(app)
    
    # Register context processors
    register_context_processors(app)
    
    return app

def register_error_handlers(app):
    """Register custom error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 Not Found errors"""
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server errors"""
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 Forbidden errors"""
        return render_template('errors/403.html'), 403

def register_template_filters(app):
    """Register custom Jinja2 template filters"""
    
    from datetime import datetime
    
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        """Format datetime objects"""
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except:
                return value
        return value.strftime(format)
    
    @app.template_filter('currency')
    def format_currency(value, currency='USD'):
        """Format currency values"""
        if value is None:
            value = 0
        
        symbols = {
            'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥',
            'CHF': 'Fr', 'AUD': 'A$', 'CAD': 'C$', 'NZD': 'NZ$'
        }
        
        symbol = symbols.get(currency, '$')
        
        # Format with comma separators
        if value >= 0:
            return f"{symbol}{value:,.2f}"
        else:
            return f"-{symbol}{abs(value):,.2f}"
    
    @app.template_filter('percentage')
    def format_percentage(value, decimals=2):
        """Format percentage values"""
        if value is None:
            return "0%"
        return f"{value:.{decimals}f}%"
    
    @app.template_filter('rr_ratio')
    def format_rr_ratio(value):
        """Format risk-reward ratio"""
        if value is None:
            return "N/A"
        return f"1:{value:.2f}"

def register_context_processors(app):
    """Register context processors to make variables available in all templates"""
    
    import random
    
    @app.context_processor
    def inject_globals():
        """Inject global variables into all templates"""
        return {
            'app_name': app.config.get('APP_NAME'),
            'app_tagline': app.config.get('APP_TAGLINE'),
            'app_version': app.config.get('APP_VERSION'),
            'random_quote': random.choice(app.config.get('QUOTES', []))
        }