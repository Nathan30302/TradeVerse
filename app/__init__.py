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
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # Ensure upload folder exists
    upload_folder = app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        os.makedirs(upload_folder, exist_ok=True)
    
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
            return user.User.query.get(int(user_id))
        
        # Create database tables
        db.create_all()
    
    # Register blueprints (routes)
    from app.routes import auth, main, trade as trade_routes, dashboard
    from app.routes import planner
    
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(trade_routes.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(planner.bp)
    
    # Register error handlers
    register_error_handlers(app)
    
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