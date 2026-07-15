"""
User Model
Handles user authentication, profile, and trading statistics
"""

from app import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
from app.utils.timeutil import utc_now
from sqlalchemy import func
from sqlalchemy import update
from sqlalchemy.orm import deferred
from app.services.entitlements import get_effective_subscription_state, user_has_feature

class User(UserMixin, db.Model):
    """
    User model for authentication and profile management
    
    This model handles all user-related data including authentication credentials,
    profile information, preferences, and provides methods for password management
    and trading statistics calculation.
    """
    
    __tablename__ = 'users'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Authentication ====================
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # ==================== Profile Information ====================
    full_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    avatar_url = db.Column(db.String(255))
    
    # ==================== Preferences ====================
    timezone = db.Column(db.String(50), default='UTC')
    preferred_currency = db.Column(db.String(3), default='USD')
    theme = db.Column(db.String(20), default='dark')  # light|dark|blue|midnight|sand
    
    # ==================== Account Status ====================
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_premium = db.Column(db.Boolean, default=False)
    # Deferred so baseline loads don't select missing columns if prod migrations lag.
    role = deferred(db.Column(db.String(20), default='user'))  # user, owner
    # ==================== Subscription & Billing ====================
    subscription_tier = deferred(db.Column(db.String(20), default='free'))  # free, pro, pro_plus, elite
    subscription_status = deferred(db.Column(db.String(20), default='active'))  # active, trialing, past_due, canceled, expired
    trial_ends_at = deferred(db.Column(db.DateTime))  # Trial expiration date
    subscription_expires_at = deferred(db.Column(db.DateTime))  # Paid subscription expiration
    stripe_customer_id = deferred(db.Column(db.String(255)))  # Stripe customer ID for payments
    # Deferred like other billing/extra columns so login SELECT works if migrations lag behind prod DB.
    weekly_focus_rule = deferred(db.Column(db.Text))  # AI Buddy weekly focus (persist via dashboard.save_weekly_focus Core UPDATE)
    exports_blocked = deferred(db.Column(db.Boolean, default=False))  # Admin-toggle: block data exports for account
    signup_utm_source = deferred(db.Column(db.String(255)))  # Optional acquisition tag (?utm_source= on signup)
    country_code = deferred(db.Column(db.String(2), nullable=True))  # ISO 3166-1 alpha-2, optional at signup
    phone_number = deferred(db.Column(db.String(32), nullable=True))  # E.164-ish stored digits/+ only

    # ==================== Timestamps ====================
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    last_login = db.Column(db.DateTime)
    
    # ==================== Relationships ====================
    trades = db.relationship('Trade', backref='trader', lazy='dynamic', 
                           cascade='all, delete-orphan')
    
    # ==================== Repr ====================
    def __repr__(self):
        return f'<User {self.username}>'
    
    # ==================== Password Methods ====================
    def set_password(self, password):
        """
        Hash and set the user's password
        
        Args:
            password (str): Plain text password
        """
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """
        Verify password against stored hash
        
        Args:
            password (str): Plain text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        return bcrypt.check_password_hash(self.password_hash, password)
    
    # ==================== Login Tracking ====================
    def update_last_login(self):
        """Persist last login by user id (works for detached / compat-loaded users)."""
        ts = utc_now()
        try:
            db.session.execute(update(User).where(User.id == self.id).values(last_login=ts))
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            raise
        try:
            self.last_login = ts
        except Exception:
            pass
    
    # ==================== Trading Statistics ====================
    def get_stats(self):
        """
        Calculate comprehensive trading statistics for the user
        
        Returns:
            dict: Dictionary containing various trading metrics including:
                - total_trades: Total number of trades
                - open_trades: Number of currently open trades
                - closed_trades: Number of closed trades
                - winning_trades: Number of profitable trades
                - losing_trades: Number of losing trades
                - win_rate: Percentage of winning trades
                - total_pnl: Total profit/loss
                - avg_win: Average profit per winning trade
                - avg_loss: Average loss per losing trade
                - avg_rr: Average risk-reward ratio
                - largest_win: Biggest winning trade
                - largest_loss: Biggest losing trade
                - profit_factor: Ratio of gross profit to gross loss
                - expectancy: Expected value per trade
        """
        from app.models.trade import Trade
        from sqlalchemy import case, and_

        empty_stats = {
            'total_trades': 0,
            'open_trades': 0,
            'closed_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_rr': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'profit_factor': 0.0,
            'expectancy': 0.0,
        }

        def _rollback_quietly():
            try:
                db.session.rollback()
            except Exception:
                pass

        cache = None
        # Request-scoped cache: dashboard + daily loop often call get_stats repeatedly.
        try:
            from flask import g, has_request_context

            if has_request_context():
                cache = getattr(g, '_tv_user_stats_cache', None)
                if cache is None:
                    g._tv_user_stats_cache = {}
                    cache = g._tv_user_stats_cache
                hit = cache.get(self.id)
                if hit is not None:
                    return dict(hit)
        except Exception:
            cache = None

        # Single aggregate query (schema-drift safe: only id/status/pnl/rr columns).
        try:
            closed_pnl = and_(Trade.status == 'CLOSED', Trade.profit_loss.isnot(None))
            row = (
                db.session.query(
                    func.count(Trade.id).label('total'),
                    func.coalesce(
                        func.sum(case((Trade.status == 'OPEN', 1), else_=0)), 0
                    ).label('open_c'),
                    func.coalesce(
                        func.sum(case((Trade.status == 'CLOSED', 1), else_=0)), 0
                    ).label('closed_c'),
                    func.coalesce(
                        func.sum(case((and_(closed_pnl, Trade.profit_loss > 0), 1), else_=0)), 0
                    ).label('wins'),
                    func.coalesce(
                        func.sum(case((and_(closed_pnl, Trade.profit_loss < 0), 1), else_=0)), 0
                    ).label('losses'),
                    func.coalesce(
                        func.sum(case((closed_pnl, 1), else_=0)), 0
                    ).label('closed_pnl_n'),
                    func.coalesce(
                        func.sum(case((closed_pnl, Trade.profit_loss), else_=0)), 0.0
                    ).label('total_pnl'),
                    func.avg(
                        case((and_(closed_pnl, Trade.profit_loss > 0), Trade.profit_loss))
                    ).label('avg_win'),
                    func.avg(
                        case((and_(closed_pnl, Trade.profit_loss < 0), -Trade.profit_loss))
                    ).label('avg_loss'),
                    func.max(
                        case((and_(closed_pnl, Trade.profit_loss > 0), Trade.profit_loss))
                    ).label('largest_win'),
                    func.max(
                        case((and_(closed_pnl, Trade.profit_loss < 0), -Trade.profit_loss))
                    ).label('largest_loss'),
                    func.avg(
                        case(
                            (
                                and_(closed_pnl, Trade.risk_reward.isnot(None)),
                                Trade.risk_reward,
                            )
                        )
                    ).label('avg_rr'),
                    func.coalesce(
                        func.sum(
                            case((and_(closed_pnl, Trade.profit_loss > 0), Trade.profit_loss), else_=0)
                        ),
                        0.0,
                    ).label('gross_profit'),
                    func.coalesce(
                        func.sum(
                            case((and_(closed_pnl, Trade.profit_loss < 0), -Trade.profit_loss), else_=0)
                        ),
                        0.0,
                    ).label('gross_loss'),
                )
                .filter(Trade.user_id == self.id)
                .one()
            )
        except Exception:
            _rollback_quietly()
            return empty_stats

        total_trades = int(row.total or 0)
        stats = dict(empty_stats)
        stats['total_trades'] = total_trades
        if total_trades == 0:
            if cache is not None:
                cache[self.id] = dict(stats)
            return stats

        stats['open_trades'] = int(row.open_c or 0)
        stats['closed_trades'] = int(row.closed_c or 0)
        closed_with_pnl = int(row.closed_pnl_n or 0)
        if closed_with_pnl == 0:
            if cache is not None:
                cache[self.id] = dict(stats)
            return stats

        wins = int(row.wins or 0)
        losses = int(row.losses or 0)
        stats['winning_trades'] = wins
        stats['losing_trades'] = losses
        stats['win_rate'] = (float(wins) / float(closed_with_pnl)) * 100.0
        stats['total_pnl'] = float(row.total_pnl or 0.0)
        if row.avg_win is not None:
            stats['avg_win'] = float(row.avg_win)
        if row.avg_loss is not None:
            stats['avg_loss'] = float(row.avg_loss)
        if row.largest_win is not None:
            stats['largest_win'] = float(row.largest_win)
        if row.largest_loss is not None:
            stats['largest_loss'] = float(row.largest_loss)
        if row.avg_rr is not None:
            stats['avg_rr'] = float(row.avg_rr)
        gp = float(row.gross_profit or 0.0)
        gl = float(row.gross_loss or 0.0)
        if gl > 0:
            stats['profit_factor'] = gp / gl
        stats['expectancy'] = stats['total_pnl'] / float(closed_with_pnl)

        if cache is not None:
            cache[self.id] = dict(stats)
        return stats

    def safe_trade_count(self) -> int:
        """
        Return a robust count of trades for this user.

        Avoids Query.count() on ORM entities which can SELECT missing columns
        when the database schema is behind migrations.
        """
        from app.models.trade import Trade

        try:
            return int(
                db.session.query(func.count(Trade.id))
                .filter(Trade.user_id == self.id)
                .scalar()
                or 0
            )
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            return 0
    
    # ==================== Recent Activity ====================
    def get_recent_trades(self, limit=10):
        """
        Get user's most recent trades
        
        Args:
            limit (int): Number of trades to return
            
        Returns:
            list: List of Trade objects
        """
        from sqlalchemy.orm import load_only
        from app.models.trade import Trade

        try:
            return (
                Trade.query.options(
                    load_only(
                        Trade.id,
                        Trade.symbol,
                        Trade.trade_type,
                        Trade.status,
                        Trade.entry_price,
                        Trade.exit_price,
                        Trade.profit_loss,
                        Trade.entry_date,
                        Trade.exit_date,
                        Trade.created_at,
                        Trade.strategy,
                        Trade.emotion,
                    )
                )
                .filter(Trade.user_id == self.id)
                .order_by(Trade.created_at.desc())
                .limit(limit)
                .all()
            )
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            return []
    
    # ==================== Trading Streaks ====================
    def get_current_streak(self):
        """
        Calculate current winning or losing streak

        Returns:
            dict: Dictionary with 'type' (win/loss) and 'count'
        """
        from sqlalchemy.orm import load_only
        from app.models.trade import Trade

        recent_trades = (
            self.trades.options(load_only(Trade.id, Trade.profit_loss, Trade.exit_date))
            .filter(
                Trade.status == 'CLOSED',
                Trade.profit_loss.isnot(None),
            )
            .order_by(db.desc('exit_date'))
            .limit(50)
            .all()
        )

        if not recent_trades:
            return {'type': None, 'count': 0}

        # Check if current streak is winning or losing
        last_trade = recent_trades[0]
        streak_type = 'win' if last_trade.profit_loss > 0 else 'loss'
        streak_count = 0

        for trade in recent_trades:
            if streak_type == 'win' and trade.profit_loss > 0:
                streak_count += 1
            elif streak_type == 'loss' and trade.profit_loss < 0:
                streak_count += 1
            else:
                break

        return {'type': streak_type, 'count': streak_count}
    
    # ==================== Utility Methods ====================
    def to_dict(self):
        """Convert user to dictionary (for API responses)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'timezone': self.timezone,
            'preferred_currency': self.preferred_currency,
            'is_premium': self.is_premium,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    # ==================== Subscription helpers ====================
    def effective_subscription(self):
        return get_effective_subscription_state(self)

    def has_feature(self, feature: str) -> bool:
        return user_has_feature(self, feature)