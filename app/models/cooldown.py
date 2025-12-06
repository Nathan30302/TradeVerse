"""
Cooldown Model
Stores impulse protection cooldown timers
"""

from app import db
from datetime import datetime, timedelta


class Cooldown(db.Model):
    """
    Stores active cooldown timers to prevent emotional trading.
    
    Cooldowns are triggered when dangerous emotions are detected.
    During a cooldown, the user cannot create new trades.
    """
    
    __tablename__ = 'cooldowns'
    
    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== Foreign Keys ====================
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # ==================== Cooldown Details ====================
    trigger_emotion = db.Column(db.String(50), nullable=False)
    trigger_reason = db.Column(db.Text)
    
    # ==================== Timing ====================
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=30)
    
    # ==================== Status ====================
    is_active = db.Column(db.Boolean, default=True)
    was_overridden = db.Column(db.Boolean, default=False)  # If user forced through
    override_reason = db.Column(db.Text)
    
    # ==================== Relationships ====================
    user = db.relationship('User', backref=db.backref('cooldowns', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Cooldown {self.trigger_emotion} until {self.expires_at}>'
    
    def is_expired(self):
        """Check if cooldown has expired"""
        return datetime.utcnow() >= self.expires_at
    
    def time_remaining(self):
        """Get remaining time in cooldown"""
        if self.is_expired():
            return timedelta(0)
        return self.expires_at - datetime.utcnow()
    
    def time_remaining_str(self):
        """Get human-readable remaining time"""
        remaining = self.time_remaining()
        
        if remaining.total_seconds() <= 0:
            return "Expired"
        
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    
    def progress_percent(self):
        """Get progress percentage (for progress bar)"""
        total_seconds = self.duration_minutes * 60
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        
        if elapsed >= total_seconds:
            return 100
        
        return int((elapsed / total_seconds) * 100)
    
    def deactivate(self):
        """Deactivate the cooldown"""
        self.is_active = False
        db.session.commit()
    
    def override(self, reason="User override"):
        """Override the cooldown (allow trading anyway)"""
        self.is_active = False
        self.was_overridden = True
        self.override_reason = reason
        db.session.commit()
    
    @staticmethod
    def get_active_cooldown(user_id):
        """Get active cooldown for a user, if any"""
        cooldown = Cooldown.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()
        
        if cooldown and cooldown.is_expired():
            cooldown.deactivate()
            return None
        
        return cooldown
    
    @staticmethod
    def create_cooldown(user_id, emotion, duration_minutes=30, reason=None):
        """Create a new cooldown for a user"""
        # Deactivate any existing cooldowns
        Cooldown.query.filter_by(user_id=user_id, is_active=True).update({'is_active': False})
        
        cooldown = Cooldown(
            user_id=user_id,
            trigger_emotion=emotion,
            trigger_reason=reason,
            duration_minutes=duration_minutes,
            expires_at=datetime.utcnow() + timedelta(minutes=duration_minutes)
        )
        
        db.session.add(cooldown)
        db.session.commit()
        
        return cooldown
    
    def to_dict(self):
        """Convert to dictionary for API"""
        return {
            'id': self.id,
            'trigger_emotion': self.trigger_emotion,
            'trigger_reason': self.trigger_reason,
            'started_at': self.started_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'duration_minutes': self.duration_minutes,
            'time_remaining': self.time_remaining_str(),
            'progress_percent': self.progress_percent(),
            'is_active': self.is_active and not self.is_expired()
        }


# Emotions that trigger cooldowns
DANGEROUS_EMOTIONS = {
    'Revenge Trading': {'duration': 60, 'severity': 'critical'},
    'Angry': {'duration': 45, 'severity': 'critical'},
    'FOMO': {'duration': 30, 'severity': 'high'},
    'Greedy': {'duration': 30, 'severity': 'high'},
    'Frustrated': {'duration': 30, 'severity': 'high'},
    'Anxious': {'duration': 20, 'severity': 'medium'},
    'Fearful': {'duration': 20, 'severity': 'medium'},
    'Tired': {'duration': 45, 'severity': 'high'},
    'Bored': {'duration': 20, 'severity': 'medium'},
}


def should_trigger_cooldown(emotion):
    """Check if an emotion should trigger a cooldown"""
    return emotion in DANGEROUS_EMOTIONS


def get_cooldown_duration(emotion):
    """Get the cooldown duration for an emotion"""
    if emotion in DANGEROUS_EMOTIONS:
        return DANGEROUS_EMOTIONS[emotion]['duration']
    return 15  # Default 15 minutes
