"""
User Model
Handles user authentication, profile, and trading statistics
"""

from app import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import func

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
    theme = db.Column(db.String(20), default='light')  # light or dark
    
    # ==================== Account Status ====================
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_premium = db.Column(db.Boolean, default=False)
    # ==================== Subscription & Billing ====================
    subscription_tier = db.Column(db.String(20), default='free')  # free, pro, elite
    subscription_status = db.Column(db.String(20), default='active')  # active, canceled, expired
    trial_ends_at = db.Column(db.DateTime)  # Trial expiration date
    subscription_expires_at = db.Column(db.DateTime)  # Paid subscription expiration
    stripe_customer_id = db.Column(db.String(255))  # Stripe customer ID for payments
    
    # ==================== Timestamps ====================
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
        """Update the last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
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
        
        # Get all trades
        all_trades = self.trades
        total_trades = all_trades.count()
        
        # Initialize default stats
        stats = {
            'total_trades': total_trades,
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
            'expectancy': 0.0
        }
        
        if total_trades == 0:
            return stats
        
        # Count open vs closed trades
        open_trades = all_trades.filter(Trade.status == 'OPEN').count()
        closed_trades = all_trades.filter(Trade.status == 'CLOSED').count()

        stats['open_trades'] = open_trades
        stats['closed_trades'] = closed_trades
        
        # Get closed trades with P/L
        closed_trades_list = all_trades.filter(
            Trade.status == 'CLOSED',
            Trade.profit_loss.isnot(None)
        ).all()
        
        # If there are no closed trades with P/L data, still return counts but keep numerical stats at defaults
        if not closed_trades_list:
            # Ensure win_rate and total_pnl are explicitly zero
            stats['win_rate'] = 0.0
            stats['total_pnl'] = 0.0
            return stats
        
        # Calculate P/L statistics
        winning_trades = [t for t in closed_trades_list if t.profit_loss > 0]
        losing_trades = [t for t in closed_trades_list if t.profit_loss < 0]
        
        stats['winning_trades'] = len(winning_trades)
        stats['losing_trades'] = len(losing_trades)
        
        # Use number of closed trades that have P/L values as the denominator for win rate and expectancy
        closed_with_pnl_count = len(closed_trades_list)

        # Win rate
        if closed_with_pnl_count > 0:
            stats['win_rate'] = (len(winning_trades) / closed_with_pnl_count) * 100
        else:
            stats['win_rate'] = 0.0

        # Total P/L - sum safely treating None as 0
        stats['total_pnl'] = sum((t.profit_loss or 0) for t in closed_trades_list)
        
        # Average win/loss
        if winning_trades:
            wins = [t.profit_loss for t in winning_trades]
            stats['avg_win'] = sum(wins) / len(wins)
            stats['largest_win'] = max(wins)
        
        if losing_trades:
            losses = [abs(t.profit_loss) for t in losing_trades]
            stats['avg_loss'] = sum(losses) / len(losses)
            stats['largest_loss'] = max(losses)
        
        # Average R:R
        rr_values = [t.risk_reward for t in closed_trades_list if t.risk_reward]
        if rr_values:
            stats['avg_rr'] = sum(rr_values) / len(rr_values)
        
        # Profit Factor (Gross Profit / Gross Loss)
        gross_profit = sum(t.profit_loss for t in winning_trades) if winning_trades else 0
        gross_loss = abs(sum(t.profit_loss for t in losing_trades)) if losing_trades else 0
        
        if gross_loss > 0:
            stats['profit_factor'] = gross_profit / gross_loss
        
        # Expectancy (Average P/L per trade) - use closed_with_pnl_count
        if closed_with_pnl_count > 0:
            stats['expectancy'] = stats['total_pnl'] / closed_with_pnl_count
        
        return stats
    
    # ==================== Recent Activity ====================
    def get_recent_trades(self, limit=10):
        """
        Get user's most recent trades
        
        Args:
            limit (int): Number of trades to return
            
        Returns:
            list: List of Trade objects
        """
        return self.trades.order_by(db.desc('created_at')).limit(limit).all()
    
    # ==================== Trading Streaks ====================
    def get_current_streak(self):
        """
        Calculate current winning or losing streak
        
        Returns:
            dict: Dictionary with 'type' (win/loss) and 'count'
        """
        from app.models.trade import Trade
        
        recent_trades = self.trades.filter(
            Trade.status == 'CLOSED',
            Trade.profit_loss.isnot(None)
        ).order_by(db.desc('exit_date')).limit(50).all()
        
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