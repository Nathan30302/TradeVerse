"""
Trade Model
Core trading journal entry with comprehensive trade tracking
"""

from app import db
from datetime import datetime
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import relationship
from app.utils.pnl_calculator import calculate_pnl, detect_asset_type, AssetType

class Trade(db.Model):
    """
    Trade model for logging and tracking individual trades
    
    This is the core model of TradeVerse. It stores all information about
    a trade including entry/exit prices, P/L calculations, risk management,
    strategy details, and psychological factors.
    """
    
    __tablename__ = 'trades'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Foreign Keys ====================
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # ==================== Basic Trade Info ====================
    symbol = db.Column(db.String(20), nullable=False, index=True)
    trade_type = db.Column(db.String(10), nullable=False)  # 'BUY' or 'SELL'
    status = db.Column(db.String(20), default='OPEN', index=True)  # 'OPEN', 'CLOSED', 'CANCELLED'
    
    # ==================== Position Details ====================
    lot_size = db.Column(db.Float, nullable=False, default=1.0)
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float)
    stop_loss = db.Column(db.Float)
    take_profit = db.Column(db.Float)
    
    # ==================== Timestamps ====================
    entry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    exit_date = db.Column(db.DateTime, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ==================== P/L & Risk ====================
    profit_loss = db.Column(db.Float)
    profit_loss_pips = db.Column(db.Float)
    risk_amount = db.Column(db.Float)  # Amount risked in account currency
    risk_percentage = db.Column(db.Float)  # Percentage of account risked
    risk_reward = db.Column(db.Float)  # R:R ratio
    commission = db.Column(db.Float, default=0.0)
    swap = db.Column(db.Float, default=0.0)
    
    # ==================== Strategy & Session ====================
    strategy = db.Column(db.String(100), index=True)
    session_type = db.Column(db.String(50))  # London, New York, Asian, etc.
    timeframe = db.Column(db.String(10))  # 1M, 5M, 15M, 1H, 4H, 1D, etc.
    
    # ==================== Psychology ====================
    emotion = db.Column(db.String(50))
    confidence_level = db.Column(db.Integer)  # 1-10 scale
    
    # ==================== Trade Quality ====================
    setup_quality = db.Column(db.Integer)  # 1-5 stars
    execution_quality = db.Column(db.Integer)  # 1-5 stars
    discipline_score = db.Column(db.Integer)  # 1-10 scale
    
    # ==================== Notes & Analysis ====================
    pre_trade_plan = db.Column(db.Text)  # What was the plan?
    post_trade_notes = db.Column(db.Text)  # What happened?
    mistakes = db.Column(db.Text)  # What went wrong?
    lessons_learned = db.Column(db.Text)  # What did you learn?
    
    # ==================== Attachments ====================
    screenshot_url = db.Column(db.String(255))
    chart_image_url = db.Column(db.String(255))
    before_screenshot = db.Column(db.String(255), nullable=True)
    after_screenshot = db.Column(db.String(255), nullable=True)
    
    # ==================== Tags & Categories ====================
    tags = db.Column(db.String(255))  # Comma-separated tags
    
    # ==================== Checklist Compliance ====================
    checklist_completed = db.Column(db.Boolean, default=False)
    playbook_followed = db.Column(db.Boolean, default=True)
    rule_violations = db.Column(db.Text)  # Which rules were broken?
    
    # ==================== Additional Metadata ====================
    broker = db.Column(db.String(50))
    account_number = db.Column(db.String(50))
    trade_id = db.Column(db.String(100))  # Broker's trade ID
    
    # ==================== Table Constraints ====================
    __table_args__ = (
        CheckConstraint('trade_type IN ("BUY", "SELL")', name='check_trade_type'),
        CheckConstraint('status IN ("OPEN", "CLOSED", "CANCELLED")', name='check_status'),
        CheckConstraint('lot_size > 0', name='check_lot_size'),
    )
    
    # ==================== Repr ====================
    def __repr__(self):
        return f'<Trade {self.symbol} {self.trade_type} @ {self.entry_price}>'
    
    # ==================== P/L Calculation ====================
    def calculate_pnl(self):
        """
        Calculate profit/loss for the trade using universal P&L calculator.
        
        Supports all asset types:
        - Forex Standard: EURUSD, GBPUSD, USDCAD, etc. (pip = 0.0001)
        - Forex JPY: USDJPY, EURJPY, etc. (pip = 0.01)
        - Indices: NAS100, US30, US500, etc.
        - Crypto: BTCUSD, ETHUSD, etc.
        - Metals: XAUUSD, XAGUSD
        
        Returns:
            float: Profit/loss amount
        """
        if not self.exit_price:
            return None
        
        # Use universal P&L calculator
        pnl, pips, asset_desc = calculate_pnl(
            symbol=self.symbol,
            trade_type=self.trade_type,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            lot_size=self.lot_size,
            commission=self.commission or 0.0,
            swap=self.swap or 0.0
        )
        
        self.profit_loss = pnl
        self.profit_loss_pips = pips
        
        return self.profit_loss
    
    def get_asset_type(self):
        """Get the asset type for this trade's symbol"""
        return detect_asset_type(self.symbol)
    
    def get_asset_type_display(self):
        """Get human-readable asset type"""
        asset_type = self.get_asset_type()
        display_names = {
            AssetType.FOREX_STANDARD: "Forex",
            AssetType.FOREX_JPY: "Forex (JPY)",
            AssetType.INDEX: "Index",
            AssetType.CRYPTO: "Crypto",
            AssetType.METAL_GOLD: "Gold",
            AssetType.METAL_SILVER: "Silver",
            AssetType.UNKNOWN: "Unknown"
        }
        return display_names.get(asset_type, "Unknown")
    
    def _is_forex_pair(self):
        """Check if symbol is a forex pair"""
        asset_type = self.get_asset_type()
        return asset_type in [AssetType.FOREX_STANDARD, AssetType.FOREX_JPY]
    
    # ==================== Risk Calculation ====================
    def calculate_risk_reward(self):
        """
        Calculate risk-reward ratio
        
        Returns:
            float: Risk-reward ratio (e.g., 2.0 means 1:2 R:R)
        """
        if not self.stop_loss or not self.take_profit:
            return None
        
        # Calculate risk (distance to SL)
        risk = abs(self.entry_price - self.stop_loss)
        
        # Calculate reward (distance to TP)
        reward = abs(self.take_profit - self.entry_price)
        
        # Calculate ratio
        if risk == 0:
            return None
        
        self.risk_reward = round(reward / risk, 2)
        return self.risk_reward
    
    def calculate_risk_amount(self, account_balance):
        """
        Calculate the amount risked in account currency
        
        Args:
            account_balance (float): Current account balance
            
        Returns:
            float: Risk amount in account currency
        """
        if not self.stop_loss:
            return None
        
        # Calculate price distance to SL
        risk_distance = abs(self.entry_price - self.stop_loss)
        
        # Calculate risk amount
        self.risk_amount = risk_distance * self.lot_size
        
        # Calculate risk percentage
        if account_balance > 0:
            self.risk_percentage = (self.risk_amount / account_balance) * 100
        
        return self.risk_amount
    
    # ==================== Trade Status Methods ====================
    def close_trade(self, exit_price, exit_date=None):
        """
        Close the trade and calculate final P/L
        
        Args:
            exit_price (float): Exit price
            exit_date (datetime, optional): Exit date/time
        """
        self.exit_price = exit_price
        self.exit_date = exit_date or datetime.utcnow()
        self.status = 'CLOSED'
        self.calculate_pnl()
        db.session.commit()
    
    def cancel_trade(self, reason=None):
        """
        Cancel the trade
        
        Args:
            reason (str, optional): Reason for cancellation
        """
        self.status = 'CANCELLED'
        if reason:
            self.post_trade_notes = f"Cancelled: {reason}\n{self.post_trade_notes or ''}"
        db.session.commit()
    
    # ==================== Trade Quality Methods ====================
    def is_winner(self):
        """Check if trade is a winner"""
        return self.profit_loss and self.profit_loss > 0
    
    def is_loser(self):
        """Check if trade is a loser"""
        return self.profit_loss and self.profit_loss < 0
    
    def is_breakeven(self):
        """Check if trade is break even"""
        return self.profit_loss == 0
    
    def get_result_emoji(self):
        """Get emoji representing trade result"""
        if not self.profit_loss:
            return '⏳'
        elif self.is_winner():
            return '✅'
        elif self.is_loser():
            return '❌'
        else:
            return '➖'
    
    # ==================== Mistake Detection ====================
    def detect_mistakes(self):
        """
        Analyze trade for common mistakes
        
        Returns:
            list: List of detected mistakes
        """
        mistakes = []
        
        # No stop loss
        if not self.stop_loss:
            mistakes.append("❌ No stop loss set - high risk!")
        
        # Poor risk-reward
        if self.risk_reward and self.risk_reward < 1.0:
            mistakes.append(f"⚠️ Poor R:R ratio (1:{self.risk_reward:.2f}) - should be at least 1:1")
        
        # High risk percentage
        if self.risk_percentage and self.risk_percentage > 2.0:
            mistakes.append(f"🚨 Risk too high ({self.risk_percentage:.1f}%) - should be max 2%")
        
        # Checklist not completed
        if not self.checklist_completed:
            mistakes.append("📋 Pre-trade checklist not completed")
        
        # Playbook not followed
        if not self.playbook_followed:
            mistakes.append("📖 Trading playbook not followed")
        
        # Emotional trading
        emotional_flags = ['Revenge Trading', 'FOMO', 'Greedy', 'Anxious', 'Fearful']
        if self.emotion in emotional_flags:
            mistakes.append(f"😰 Emotional trading detected: {self.emotion}")
        
        # Moving stop loss (if notes mention it)
        if self.post_trade_notes and 'moved stop' in self.post_trade_notes.lower():
            mistakes.append("🔄 Stop loss was moved (against the plan)")
        
        return mistakes
    
    # ==================== Trade Duration ====================
    def get_duration(self):
        """
        Calculate how long the trade was held
        
        Returns:
            str: Human-readable duration
        """
        if not self.exit_date:
            return "Still open"
        
        duration = self.exit_date - self.entry_date
        
        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    # ==================== Plan Methods ====================
    def has_plan(self):
        """Check if trade has an associated plan"""
        if self.plan is None:
            return False
        # Handle both list and single object relationships
        if hasattr(self.plan, '__iter__') and not isinstance(self.plan, str):
            return len(self.plan) > 0
        return True
    
    def get_plan(self):
        """Get the trade plan, handling both list and single object"""
        if not self.has_plan():
            return None
        if hasattr(self.plan, '__iter__') and not isinstance(self.plan, str):
            return self.plan[0] if len(self.plan) > 0 else None
        return self.plan
    
    # ==================== Utility Methods ====================
    def to_dict(self):
        """Convert trade to dictionary (for API responses)"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'trade_type': self.trade_type,
            'status': self.status,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'lot_size': self.lot_size,
            'profit_loss': self.profit_loss,
            'risk_reward': self.risk_reward,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'exit_date': self.exit_date.isoformat() if self.exit_date else None,
            'strategy': self.strategy,
            'emotion': self.emotion,
            'is_winner': self.is_winner()
        }