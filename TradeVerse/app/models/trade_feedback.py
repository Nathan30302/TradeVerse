"""
Trade Feedback Model
Stores AI-generated feedback for trades based on rule compliance and patterns
"""

from app import db
from datetime import datetime


class TradeFeedback(db.Model):
    """
    Stores automated feedback generated for each trade.
    Feedback is based on rule compliance, plan adherence, and trading patterns.
    """
    
    __tablename__ = 'trade_feedbacks'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Foreign Keys ====================
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # ==================== Feedback Content ====================
    feedback_type = db.Column(db.String(20), nullable=False)  # 'positive', 'warning', 'critical'
    category = db.Column(db.String(50), nullable=False)  # 'risk', 'discipline', 'emotion', 'execution', 'plan'
    message = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(10), default='📝')  # Emoji icon for display
    
    # ==================== Scoring ====================
    impact_score = db.Column(db.Integer, default=0)  # -10 to +10 impact on performance
    
    # ==================== Timestamps ====================
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # ==================== Relationships ====================
    trade = db.relationship('Trade', backref=db.backref('feedbacks', lazy='dynamic', cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<TradeFeedback {self.feedback_type}: {self.message[:30]}...>'
    
    @staticmethod
    def get_icon_for_type(feedback_type):
        """Get appropriate icon based on feedback type"""
        icons = {
            'positive': '✅',
            'warning': '⚠️',
            'critical': '🚨'
        }
        return icons.get(feedback_type, '📝')
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'feedback_type': self.feedback_type,
            'category': self.category,
            'message': self.message,
            'icon': self.icon,
            'impact_score': self.impact_score,
            'created_at': self.created_at.isoformat()
        }
