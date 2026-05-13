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
    # Optional override for /owner/unlock; if unset, unlock compares against SECRET_KEY (Render-friendly).
    OWNER_ADMIN_TOKEN = os.environ.get('OWNER_ADMIN_TOKEN')
    # Query-token access for legacy /admin/stats?admin_token=... (prefer ADMIN_TOKEN; else OWNER_ADMIN_TOKEN).
    ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN')
    
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
    # Screenshots use png/jpg/webp/heic; pdf kept for other uploads (e.g. statements).
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'pdf'}
    
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

    # UI themes (order preserved for pickers)
    UI_THEME_CHOICES = ('light', 'dark', 'blue', 'midnight', 'sand')
    ALLOWED_UI_THEMES = frozenset(UI_THEME_CHOICES)

    # Public support contact (mailto + footer). Override via SUPPORT_EMAIL if needed.
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL') or 'tradeversesupport@gmail.com'
    # Traders Discord community (footer + landing). Unset = default invite; DISCORD_COMMUNITY_URL= hides links.
    _discord_env = os.environ.get('DISCORD_COMMUNITY_URL')
    if _discord_env is None:
        DISCORD_COMMUNITY_URL = 'https://discord.gg/avZdspg2H'
    else:
        DISCORD_COMMUNITY_URL = _discord_env.strip()
    # Optional canonical origin (https://yourdomain.com, no trailing slash).
    # Set in production for: transactional emails, sitemap/robots, and <link rel="canonical">
    # so they match your Google Search Console property (reduces redirect / duplicate URL issues).
    PUBLIC_SITE_URL = (os.environ.get('PUBLIC_SITE_URL') or '').strip().rstrip('/')
    
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
        'Angry',
        'Greedy',
        'Revenge Trading',
        'FOMO',
        'FOMO (Fear of Missing Out)',
        'Overconfident',
        'Frustrated',
        'Disciplined',
        'Patient',
        'Impulsive',
        'Tired',
        'Bored',
    ]

    # --- Impulse protection (cooldown) — single source of truth for rules ---
    # Emotions listed here never start a cooldown (aligned with EMOTIONS pick-list).
    COOLDOWN_EMOTIONS_EXEMPT = frozenset(
        {'Confident', 'Calm & Focused', 'Disciplined', 'Patient'}
    )
    # Map emotion label → minutes (and severity for UI). Keys must match EMOTIONS strings exactly.
    COOLDOWN_EMOTION_RULES = {
        'Revenge Trading': {'duration': 60, 'severity': 'critical'},
        'Angry': {'duration': 45, 'severity': 'critical'},
        'Tired': {'duration': 45, 'severity': 'high'},
        'Overconfident': {'duration': 35, 'severity': 'high'},
        'FOMO': {'duration': 30, 'severity': 'high'},
        'FOMO (Fear of Missing Out)': {'duration': 30, 'severity': 'high'},
        'Greedy': {'duration': 30, 'severity': 'high'},
        'Frustrated': {'duration': 30, 'severity': 'high'},
        'Impulsive': {'duration': 30, 'severity': 'high'},
        'Excited': {'duration': 25, 'severity': 'high'},
        'Anxious': {'duration': 20, 'severity': 'medium'},
        'Fearful': {'duration': 20, 'severity': 'medium'},
        'Nervous': {'duration': 20, 'severity': 'medium'},
        'Bored': {'duration': 20, 'severity': 'medium'},
    }
    COOLDOWN_DEFAULT_DURATION_MINUTES = 15
    # Consecutive CLOSED losses (by exit_date) required to trigger loss-streak cooldown.
    COOLDOWN_LOSS_STREAK_TRADES = 2
    COOLDOWN_LOSS_STREAK_MINUTES = 45
    COOLDOWN_LOSS_STREAK_LOOKBACK_DAYS = 14
    # Override abuse limits (rolling windows).
    COOLDOWN_OVERRIDE_MAX_PER_DAY = 1
    COOLDOWN_OVERRIDE_MAX_PER_WEEK = 3
    COOLDOWN_OVERRIDE_WINDOW_DAYS = 7
    # If discipline_score (1–10) is at or below this after save/edit, trigger impulse cooldown (rule-breaking).
    COOLDOWN_LOW_DISCIPLINE_THRESHOLD = 3

    # Map shorthand / legacy labels → canonical EMOTIONS / cooldown keys (lowercase keys).
    COOLDOWN_EMOTION_ALIASES = {
        'revenge': 'Revenge Trading',
        'revenge trading': 'Revenge Trading',
        'calm': 'Calm & Focused',
        'focused': 'Calm & Focused',
        'calm focused': 'Calm & Focused',
        'fomo': 'FOMO',
        'over trading': 'Impulsive',
        'overtrading': 'Impulsive',
        'chasing': 'Impulsive',
        'broke rules': 'Impulsive',
        'break rules': 'Impulsive',
    }

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
    
    # Available Currencies (profile drop-downs)
    CURRENCIES = ['USD', 'ZAR', 'ZMW', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD']

    # Allowed preferred_currency values (3-letter ISO for DB column)
    DISPLAY_CURRENCIES = ('USD', 'ZAR', 'ZMW', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD')

    # Registration / profile: ISO 3166-1 alpha-2 (first element '' = prefer not to say)
    REGISTER_COUNTRY_CHOICES = (
        ('', 'Prefer not to say'),
        ('ZM', 'Zambia'),
        ('ZA', 'South Africa'),
        ('US', 'United States'),
        ('GB', 'United Kingdom'),
        ('DE', 'Germany'),
        ('FR', 'France'),
        ('NG', 'Nigeria'),
        ('KE', 'Kenya'),
        ('IN', 'India'),
        ('AU', 'Australia'),
        ('CA', 'Canada'),
        ('BR', 'Brazil'),
        ('AE', 'United Arab Emirates'),
        ('SG', 'Singapore'),
        ('JP', 'Japan'),
        ('CN', 'China'),
        ('NL', 'Netherlands'),
        ('ES', 'Spain'),
        ('IT', 'Italy'),
        ('PT', 'Portugal'),
    )
    
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

    # Feature flags (set to 0/false to disable surfaces quickly)
    FEATURE_AI_BUDDY = os.environ.get('FEATURE_AI_BUDDY', 'true').lower() in ('1', 'true', 'yes')
    FEATURE_MARKET_QUOTES = os.environ.get('FEATURE_MARKET_QUOTES', 'true').lower() in ('1', 'true', 'yes')
    # Optional: enable web-enabled AI answers (OpenAI + Tavily). If false, AI Buddy uses local coach only.
    FEATURE_AI_WEB = os.environ.get('FEATURE_AI_WEB', 'false').lower() in ('1', 'true', 'yes')

    # Public market-quotes endpoint: max requests per IP per rolling minute
    MARKET_QUOTES_MAX_PER_MINUTE = int(os.environ.get('MARKET_QUOTES_MAX_PER_MINUTE', '120'))

    # Performance toggles
    ENABLE_FTS_BUILD = True

    # Prometheus /metrics WSGI mount (see README_DEPLOY). Disabled unless explicitly enabled.
    PROMETHEUS_METRICS_ENABLED = os.environ.get('PROMETHEUS_METRICS_ENABLED', '').lower() in (
        '1', 'true', 'yes'
    )

    # Email summaries
    WEEKLY_SUMMARY_SENDER = os.environ.get('WEEKLY_SUMMARY_SENDER') or os.environ.get('MAIL_USERNAME')

    # Owner console bulk email safety cap (per POST request)
    OWNER_EMAIL_MAX_PER_RUN = int(os.environ.get('OWNER_EMAIL_MAX_PER_RUN', '200'))

    # Short-lived admin URL (?admin_ts=) max age in seconds (signed with SECRET_KEY).
    ADMIN_TIMED_LINK_MAX_AGE = int(os.environ.get('ADMIN_TIMED_LINK_MAX_AGE', '3600'))

    # Optional global banner (exports still served; use for warnings before deploys).
    MAINTENANCE_MODE = os.environ.get('MAINTENANCE_MODE', '').lower() in ('1', 'true', 'yes')

    # Market data
    MARKET_DATA_PROVIDER = os.environ.get('MARKET_DATA_PROVIDER') or 'twelvedata'

class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    # Off by default: SQL echo floods logs and slows every request. Set SQLALCHEMY_ECHO=1 to debug SQL.
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', '').lower() in ('1', 'true', 'yes')
    PROMETHEUS_METRICS_ENABLED = True

class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Require HTTPS
    SQLALCHEMY_ECHO = False
    
    # Secrets MUST be provided via environment variables in production.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    OWNER_ADMIN_TOKEN = os.environ.get('OWNER_ADMIN_TOKEN')
    ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN')
    
    # Database MUST be provided via environment variable in production.
    SQLALCHEMY_DATABASE_URI = fix_database_url(os.environ.get('DATABASE_URL'))

    # Cookie hardening (HTTPS-only in production)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Avoid expensive runtime index builds in production.
    ENABLE_FTS_BUILD = False

    PROMETHEUS_METRICS_ENABLED = os.environ.get('PROMETHEUS_METRICS_ENABLED', '').lower() in (
        '1', 'true', 'yes'
    )

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
    PROMETHEUS_METRICS_ENABLED = False
    MAINTENANCE_MODE = False

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}