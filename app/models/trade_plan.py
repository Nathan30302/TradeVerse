"""
Trade Plan Model
Stores pre-trade planning and post-trade review
"""

from app import db
from datetime import datetime
from app.utils.pnl_calculator import calculate_pnl as calc_pnl, detect_asset_type

class TradePlan(db.Model):
    """
    Trade Plan model for planning before trade and reviewing after
    Redesigned for a complete Before/After workflow
    """
    
    __tablename__ = 'trade_plans'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Foreign Keys ====================
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), unique=True, nullable=True)
    
    # ==================== Status ====================
    status = db.Column(db.String(20), default='PLANNING', index=True)  # PLANNING, EXECUTED, REVIEWED
    
    # ==================== BEFORE TRADE (Pre-Trade Planning) ====================
    # Basic Trade Info
    symbol = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)  # BUY or SELL
    
    # Planned Levels
    planned_entry = db.Column(db.Float)
    planned_stop_loss = db.Column(db.Float)
    planned_take_profit = db.Column(db.Float)
    planned_lot_size = db.Column(db.Float, default=0.01)
    planned_rr_ratio = db.Column(db.Float)  # Auto-calculated
    
    # Strategy
    strategy = db.Column(db.String(50))  # Breakout, Retest, SMC, etc.
    
    # Checklist (Toggles)
    market_structure_confirmed = db.Column(db.Boolean, default=False)
    liquidity_taken = db.Column(db.Boolean, default=False)
    confirmation_candle_formed = db.Column(db.Boolean, default=False)
    session_aligned = db.Column(db.Boolean, default=False)
    
    # Screenshots
    screenshot_before_path = db.Column(db.String(500))
    
    # Pre-trade notes
    pre_trade_notes = db.Column(db.Text)
    
    # Legacy fields (keeping for backwards compatibility)
    market_bias = db.Column(db.String(20))
    setup_type = db.Column(db.String(50))
    confluence_score = db.Column(db.Integer)
    planned_risk_percentage = db.Column(db.Float)
    emotion_before = db.Column(db.String(50))
    emotion_intensity_before = db.Column(db.Integer)
    key_levels = db.Column(db.Text)
    trade_hypothesis = db.Column(db.Text)
    
    # ==================== AFTER TRADE (Post-Trade Review) ====================
    # Actual Execution
    actual_entry = db.Column(db.Float)
    actual_exit = db.Column(db.Float)
    actual_pnl = db.Column(db.Float)  # Auto-calculated
    
    # Emotion
    emotion_after = db.Column(db.String(50))
    
    # Trade Grade
    trade_grade = db.Column(db.String(1))  # A, B, C, D
    
    # Screenshot after
    screenshot_after_path = db.Column(db.String(500))
    
    # Reflection notes
    reflection_notes = db.Column(db.Text)
    
    # Legacy review fields
    execution_notes = db.Column(db.Text)
    trade_result = db.Column(db.String(20))
    followed_entry = db.Column(db.Boolean, default=True)
    followed_stop_loss = db.Column(db.Boolean, default=True)
    followed_take_profit = db.Column(db.Boolean, default=True)
    moved_stop_loss = db.Column(db.Boolean, default=False)
    mistakes_made = db.Column(db.Text)
    lessons_learned = db.Column(db.Text)
    what_went_well = db.Column(db.Text)
    what_went_wrong = db.Column(db.Text)
    emotion_intensity_after = db.Column(db.Integer)
    
    # ==================== Quality Scores ====================
    plan_quality_score = db.Column(db.Integer)
    execution_quality_score = db.Column(db.Integer)
    
    # ==================== Timestamps ====================
    planned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    executed_at = db.Column(db.DateTime)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ==================== Execution Link (new) ====================
    # Flag to indicate this plan was executed into a Trade record
    executed = db.Column(db.Boolean, default=False, nullable=False)
    # Link to the Trade created when executing this plan (optional, non-unique)
    executed_trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), nullable=True)
    
    # ==================== Relationships ====================
    # Relationship to legacy linked Trade (uses trade_id)
    trade = db.relationship('Trade', foreign_keys=[trade_id], backref=db.backref('plan', uselist=False), uselist=False)
    # Relationship to the Trade created when executing this plan
    executed_trade = db.relationship('Trade', foreign_keys=[executed_trade_id], backref=db.backref('executed_plan', uselist=False), uselist=False)
    user = db.relationship('User', backref='trade_plans')
    
    # ==================== Methods ====================
    def __repr__(self):
        return f'<TradePlan {self.symbol} {self.direction} - {self.status}>'
    
    def calculate_planned_rr(self):
        """Auto-calculate planned risk-reward ratio"""
        if not all([self.planned_entry, self.planned_stop_loss, self.planned_take_profit]):
            return None
        
        risk = abs(self.planned_entry - self.planned_stop_loss)
        reward = abs(self.planned_take_profit - self.planned_entry)
        
        if risk == 0:
            return None
        
        self.planned_rr_ratio = round(reward / risk, 2)
        return self.planned_rr_ratio
    
    def calculate_pnl(self, entry_price=None, exit_price=None, lot_size=None):
        """
        Calculate P&L using universal P&L calculator.
        
        Supports all asset types:
        - Forex (Standard & JPY pairs)
        - Indices (NAS100, US30, etc.)
        - Crypto (BTCUSD, ETHUSD, etc.)
        - Metals (XAUUSD, XAGUSD)
        """
        entry = entry_price or self.actual_entry
        exit_p = exit_price or self.actual_exit
        lot = lot_size or self.planned_lot_size
        
        if not all([entry, exit_p, lot]):
            return None
        
        # Use universal P&L calculator
        pnl, pips, asset_desc = calc_pnl(
            symbol=self.symbol or 'XAUUSD',
            trade_type=self.direction or 'BUY',
            entry_price=entry,
            exit_price=exit_p,
            lot_size=lot
        )
        
        self.actual_pnl = pnl
        return self.actual_pnl
    
    def get_checklist_score(self):
        """Calculate checklist completion score"""
        checks = [
            self.market_structure_confirmed,
            self.liquidity_taken,
            self.confirmation_candle_formed,
            self.session_aligned
        ]
        return sum(1 for c in checks if c)
    
    def get_checklist_percentage(self):
        """Get checklist completion as percentage"""
        return (self.get_checklist_score() / 4) * 100
    
    def calculate_plan_quality(self):
        """Calculate plan quality score based on completeness"""
        score = 0
        
        # Basic info (30 points)
        if self.symbol:
            score += 10
        if self.direction:
            score += 10
        if self.strategy:
            score += 10
        
        # Entry plan (30 points)
        if self.planned_entry:
            score += 10
        if self.planned_stop_loss:
            score += 10
        if self.planned_take_profit:
            score += 10
        
        # Risk management (20 points)
        if self.planned_lot_size:
            score += 10
        if self.planned_rr_ratio and self.planned_rr_ratio >= 1:
            score += 10
        
        # Checklist (10 points)
        checklist_score = self.get_checklist_score()
        score += (checklist_score / 4) * 10
        
        # Documentation (10 points)
        if self.pre_trade_notes:
            score += 5
        if self.screenshot_before_path:
            score += 5
        
        self.plan_quality_score = int(score)
        return self.plan_quality_score
    
    def calculate_execution_quality(self):
        """Calculate execution quality based on plan adherence"""
        if self.status != 'REVIEWED':
            return 0
        
        score = 100
        
        # Deduct for rule violations
        if not self.followed_entry:
            score -= 20
        if not self.followed_stop_loss:
            score -= 30
        if not self.followed_take_profit:
            score -= 10
        if self.moved_stop_loss:
            score -= 25
        
        # Bonus for good documentation
        if self.reflection_notes:
            score += 5
        if self.screenshot_after_path:
            score += 5
        
        score = min(max(score, 0), 100)
        self.execution_quality_score = score
        return score
    
    def mark_as_executed(self):
        """Mark plan as executed and transition status"""
        self.status = 'EXECUTED'
        self.executed_at = datetime.utcnow()
    
    def mark_as_reviewed(self):
        """Mark plan as reviewed and transition status"""
        self.status = 'REVIEWED'
        self.reviewed_at = datetime.utcnow()
    
    def is_planning(self):
        return self.status == 'PLANNING'
    
    def is_executed(self):
        return self.status == 'EXECUTED'
    
    def is_reviewed(self):
        return self.status == 'REVIEWED'
    
    def is_complete(self):
        """Check if post-trade review is complete"""
        return self.reviewed_at is not None
    
    def get_compliance_issues(self):
        """Get list of rule violations"""
        issues = []
        
        if not self.followed_entry:
            issues.append("❌ Did not enter at planned price")
        if not self.followed_stop_loss:
            issues.append("❌ Did not respect stop loss")
        if not self.followed_take_profit:
            issues.append("❌ Did not take profit as planned")
        if self.moved_stop_loss:
            issues.append("🚨 MOVED STOP LOSS (Major violation!)")
        
        if not issues:
            issues.append("✅ Perfect execution - followed the plan!")
        
        return issues
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'direction': self.direction,
            'status': self.status,
            'planned_entry': self.planned_entry,
            'planned_stop_loss': self.planned_stop_loss,
            'planned_take_profit': self.planned_take_profit,
            'planned_lot_size': self.planned_lot_size,
            'planned_rr_ratio': self.planned_rr_ratio,
            'strategy': self.strategy,
            'actual_entry': self.actual_entry,
            'actual_exit': self.actual_exit,
            'actual_pnl': self.actual_pnl,
            'trade_grade': self.trade_grade,
            'planned_at': self.planned_at.isoformat() if self.planned_at else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }
