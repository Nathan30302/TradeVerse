"""
TradeVerse Configuration
Professional configuration management for different environments
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Helper function to fix database URL for SQLAlchemy 2.0
def fix_database_url(url):
    """Convert postgres:// to postgresql:// for SQLAlchemy 2.0 compatibility"""
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url

class Config:
    """Base configuration - shared across all environments"""
    
    # Flask Core
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-please-change-in-production'
    
    # Database - Fix URL scheme for SQLAlchemy 2.0
    _raw_db_url = os.environ.get('DATABASE_URL') or 'sqlite:///tradeverse.db'
    SQLALCHEMY_DATABASE_URI = fix_database_url(_raw_db_url)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Set to True to see SQL queries
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # WTForms Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No time limit on CSRF tokens
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
    
    # Pagination
    ITEMS_PER_PAGE = 20
    
    # Email Configuration (for password reset)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')
    
    # Application Settings
    APP_NAME = 'TradeVerse'
    APP_TAGLINE = 'Professional Trading Journal'
    APP_VERSION = '2.0.0'
    
    # Trading Instruments
    INSTRUMENTS = [
        # Forex Major Pairs
        'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD',
        # Forex Minor Pairs
        'EURGBP', 'EURJPY', 'GBPJPY', 'EURCHF', 'EURAUD', 'EURCAD', 'GBPAUD',
        # Commodities
        'XAUUSD', 'XAGUSD', 'USOIL', 'UKOIL', 'COPPER', 'NATGAS',
        # Indices
        'US30', 'US100', 'US500', 'DE30', 'UK100', 'JP225', 'AUS200',
        # Crypto
        'BTCUSD', 'ETHUSD', 'BNBUSD', 'XRPUSD', 'SOLUSD', 'ADAUSD'
    ]
    
    # Trading Strategies
    STRATEGIES = [
        'Price Action',
        'Support & Resistance',
        'Trend Following',
        'Breakout Trading',
        'Scalping',
        'Day Trading',
        'Swing Trading',
        'Mean Reversion',
        'Supply & Demand',
        'Smart Money Concepts (SMC)',
        'ICT Concepts',
        'Fibonacci Trading',
        'News Trading',
        'Grid Trading',
        'Hedging',
        'Other'
    ]
    
    # Trading Emotions
    EMOTIONS = [
        'Confident',
        'Calm & Focused',
        'Excited',
        'Nervous',
        'Anxious',
        'Fearful',
        'Greedy',
        'Revenge Trading',
        'FOMO (Fear of Missing Out)',
        'Overconfident',
        'Frustrated',
        'Disciplined',
        'Patient',
        'Impulsive'
    ]
    
    # Session Types
    SESSION_TYPES = [
        'London Session',
        'New York Session',
        'Asian Session',
        'Sydney Session',
        'Overlap Sessions'
    ]
    
    # Available Timezones
    TIMEZONES = [
        'UTC',
        'US/Eastern',
        'US/Central',
        'US/Mountain',
        'US/Pacific',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Asia/Tokyo',
        'Asia/Shanghai',
        'Asia/Hong_Kong',
        'Asia/Singapore',
        'Australia/Sydney'
    ]
    
    # Available Currencies
    CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD']
    
    # Motivational Trading Quotes
    QUOTES = [
        # Discipline & Process
        "The goal of a successful trader is to make the best trades. Money is secondary.",
        "Plan your trade, trade your plan.",
        "The best traders are the most disciplined traders.",
        "Success in trading is about consistency, not perfection.",
        "Discipline is the bridge between your goals and your results.",
        "Your process defines your profits. Trust the system.",
        "Stick to the rules, even when it's hard—especially when it's hard.",
        
        # Risk Management
        "Risk comes from not knowing what you're doing.",
        "Cut your losses short, let your profits run.",
        "Protect your capital first. Profits will follow.",
        "The first rule of trading: never lose money. The second rule: never forget rule one.",
        "Position sizing is the silent key to survival.",
        
        # Patience & Mindset
        "The market is a device for transferring money from the impatient to the patient.",
        "Waiting for the right setup is a skill, not a weakness.",
        "Boredom is the enemy of good trading. Embrace stillness.",
        "The market rewards those who wait for clarity.",
        "Patience is not passive—it's strategic.",
        
        # Market Wisdom
        "Every battle is won before it is fought.",
        "Markets are never wrong – opinions often are.",
        "It's not whether you're right or wrong, but how much you make when you're right.",
        "Trade what you see, not what you think.",
        "The trend is your friend until the end.",
        "In trading, the impossible happens about twice a year.",
        
        # Emotional Control
        "Fear and greed are the trader's worst enemies. Master them.",
        "Your emotions are data—observe them, don't obey them.",
        "Revenge trading turns one bad trade into many.",
        "Take a break before you break your account.",
        "A calm mind makes profitable decisions.",
        
        # Growth & Learning
        "Every losing trade is tuition. Learn the lesson.",
        "Journal your trades. Your past self is your best teacher.",
        "The best investment you can make is in yourself.",
        "Winners focus on process. Losers focus on outcomes.",
        "Small consistent gains beat big risky bets."
    ]
    
    # Quote rotation interval in milliseconds (30 seconds)
    QUOTE_ROTATION_INTERVAL = 30000

class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Show SQL queries in development

class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Require HTTPS
    SQLALCHEMY_ECHO = False
    
    # Secret key must be provided via environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # Fallback for first deployment only, should be overridden immediately
        SECRET_KEY = 'prod-key-change-me-immediately'
    
    # Database must be provided via environment variable (Render PostgreSQL)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///tradeverse.db')
    
    # Use /tmp for ephemeral file uploads in cloud environments
    UPLOAD_FOLDER = '/tmp/uploads'
    TRADE_SCREENSHOTS_FOLDER = '/tmp/uploads/trade_screenshots'
    
    # Ensure /tmp directories exist
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(TRADE_SCREENSHOTS_FOLDER, exist_ok=True)
    except Exception:
        pass

class TestingConfig(Config):
    """Testing environment configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Use in-memory database for tests
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
# Add this to your existing Config class in config.py

# File Upload Configuration (if not already there)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
TRADE_SCREENSHOTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'trade_screenshots')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size