"""
Cooldown Model
Stores impulse protection cooldown timers.
Rules (durations, exempt emotions, defaults) live in config.Config — see COOLDOWN_* keys.
"""

from app import db
from datetime import datetime, timedelta


class Cooldown(db.Model):
    """
    Stores active cooldown timers to prevent emotional trading.

    Cooldowns are triggered when dangerous emotions are detected or after loss streaks.
    During a cooldown, the user cannot create new trades (unless they override with limits).
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
        ).order_by(Cooldown.started_at.desc()).first()

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


def _config():
    """Flask config when in app context; else base Config class."""
    try:
        from flask import has_request_context, current_app

        if has_request_context():
            return current_app.config
    except RuntimeError:
        pass
    return None


def cooldown_emotion_rules():
    """
    Emotion → {duration, severity} map. Prefer app.config.COOLDOWN_EMOTION_RULES when bound.
    """
    cfg = _config()
    if cfg and isinstance(cfg.get('COOLDOWN_EMOTION_RULES'), dict) and cfg['COOLDOWN_EMOTION_RULES']:
        return dict(cfg['COOLDOWN_EMOTION_RULES'])
    from config import Config

    return dict(Config.COOLDOWN_EMOTION_RULES)


def cooldown_emotions_exempt():
    cfg = _config()
    if cfg and cfg.get('COOLDOWN_EMOTIONS_EXEMPT'):
        return frozenset(cfg['COOLDOWN_EMOTIONS_EXEMPT'])
    from config import Config

    return frozenset(Config.COOLDOWN_EMOTIONS_EXEMPT)


def _emotion_aliases():
    cfg = _config()
    if cfg and isinstance(cfg.get('COOLDOWN_EMOTION_ALIASES'), dict):
        return {str(k).strip().lower(): v for k, v in cfg['COOLDOWN_EMOTION_ALIASES'].items()}
    from config import Config

    return {str(k).strip().lower(): v for k, v in Config.COOLDOWN_EMOTION_ALIASES.items()}


def normalize_emotion_for_cooldown(emotion):
    """
    Return canonical dict key for this emotion, or None if empty / only whitespace.
    Matches config keys case-insensitively; normalizes FOMO variants.
    """
    if not emotion:
        return None
    raw = str(emotion).strip()
    if not raw:
        return None

    low = raw.lower()
    aliases = _emotion_aliases()
    if low in aliases:
        raw = aliases[low]

    rules = cooldown_emotion_rules()
    if raw in rules:
        return raw

    low = raw.lower()
    for key in rules:
        if key.lower() == low:
            return key

    if low.startswith('fomo'):
        if 'FOMO (Fear of Missing Out)' in rules and '(' in raw:
            return 'FOMO (Fear of Missing Out)'
        if 'FOMO' in rules:
            return 'FOMO'
    return raw


def should_trigger_cooldown(emotion):
    """True if this emotion is in rules and not in the exempt set."""
    e = normalize_emotion_for_cooldown(emotion)
    if not e:
        return False
    if e in cooldown_emotions_exempt():
        return False
    return e in cooldown_emotion_rules()


def get_cooldown_duration(emotion):
    """Cooldown length in minutes for this emotion."""
    e = normalize_emotion_for_cooldown(emotion)
    rules = cooldown_emotion_rules()
    if e in rules:
        return int(rules[e]['duration'])
    cfg = _config()
    if cfg and cfg.get('COOLDOWN_DEFAULT_DURATION_MINUTES') is not None:
        return int(cfg['COOLDOWN_DEFAULT_DURATION_MINUTES'])
    from config import Config

    return int(Config.COOLDOWN_DEFAULT_DURATION_MINUTES)


def cooldown_rule_rows_for_template():
    """Sorted rows for help / settings UI: list of dicts name, minutes, severity."""
    rules = cooldown_emotion_rules()
    rows = [
        {'name': name, 'minutes': int(meta['duration']), 'severity': meta.get('severity', 'medium')}
        for name, meta in rules.items()
    ]
    rows.sort(key=lambda r: (-r['minutes'], r['name'].lower()))
    return rows


# Back-compat for imports expecting a module-level dict name
DANGEROUS_EMOTIONS = cooldown_emotion_rules()
