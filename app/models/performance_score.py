"""
Performance Score Model
Stores weekly performance scores based on trading metrics
"""

from app import db
from datetime import datetime, timedelta


class PerformanceScore(db.Model):
    """
    Stores calculated weekly performance scores.
    Scores are based on rule compliance, RR quality, emotional state, and consistency.
    """
    
    __tablename__ = 'performance_scores'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Foreign Keys ====================
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # ==================== Week Identifier ====================
    week_start = db.Column(db.Date, nullable=False, index=True)
    week_end = db.Column(db.Date, nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    
    # ==================== Overall Score ====================
    overall_score = db.Column(db.Float, default=0.0)  # 0-100
    grade = db.Column(db.String(2))  # A+, A, B+, B, C+, C, D, F
    
    # ==================== Component Scores (0-100 each) ====================
    rule_compliance_score = db.Column(db.Float, default=0.0)
    rr_quality_score = db.Column(db.Float, default=0.0)
    emotional_score = db.Column(db.Float, default=0.0)
    consistency_score = db.Column(db.Float, default=0.0)
    discipline_score = db.Column(db.Float, default=0.0)
    
    # ==================== Trade Statistics ====================
    total_trades = db.Column(db.Integer, default=0)
    winning_trades = db.Column(db.Integer, default=0)
    losing_trades = db.Column(db.Integer, default=0)
    win_rate = db.Column(db.Float, default=0.0)
    total_pnl = db.Column(db.Float, default=0.0)
    avg_rr = db.Column(db.Float, default=0.0)
    
    # ==================== Timestamps ====================
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # ==================== Unique Constraint ====================
    __table_args__ = (
        db.UniqueConstraint('user_id', 'week_start', name='unique_user_week'),
    )
    
    def __repr__(self):
        return f'<PerformanceScore Week {self.week_number}/{self.year}: {self.overall_score}>'
    
    @staticmethod
    def get_grade(score):
        """Convert numeric score to letter grade"""
        if score >= 95:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 85:
            return 'B+'
        elif score >= 80:
            return 'B'
        elif score >= 75:
            return 'C+'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    @staticmethod
    def get_grade_color(grade):
        """Get Bootstrap color class for grade"""
        colors = {
            'A+': 'success',
            'A': 'success',
            'B+': 'info',
            'B': 'info',
            'C+': 'warning',
            'C': 'warning',
            'D': 'danger',
            'F': 'danger'
        }
        return colors.get(grade, 'secondary')
    
    def to_dict(self):
        """Convert to dictionary for API/charts"""
        return {
            'id': self.id,
            'week_start': self.week_start.isoformat(),
            'week_end': self.week_end.isoformat(),
            'week_number': self.week_number,
            'year': self.year,
            'overall_score': round(self.overall_score, 1),
            'grade': self.grade,
            'rule_compliance_score': round(self.rule_compliance_score, 1),
            'rr_quality_score': round(self.rr_quality_score, 1),
            'emotional_score': round(self.emotional_score, 1),
            'consistency_score': round(self.consistency_score, 1),
            'discipline_score': round(self.discipline_score, 1),
            'total_trades': self.total_trades,
            'win_rate': round(self.win_rate, 1),
            'total_pnl': round(self.total_pnl, 2)
        }
