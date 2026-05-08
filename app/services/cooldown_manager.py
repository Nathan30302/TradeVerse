"""
Cooldown Manager
Manages impulse protection cooldowns
"""

from app import db
from app.models.cooldown import Cooldown, DANGEROUS_EMOTIONS, should_trigger_cooldown, get_cooldown_duration
from datetime import datetime
from datetime import timedelta
from app.models.trade import Trade


class CooldownManager:
    """
    Manages the impulse protection cooldown system.
    
    Features:
    - Triggers cooldowns when dangerous emotions are detected
    - Blocks trade creation during active cooldowns
    - Allows emergency overrides (logged for review)
    - Tracks cooldown history
    """
    
    def __init__(self, user_id):
        self.user_id = user_id
    
    def get_active_cooldown(self):
        """Get active cooldown for user"""
        return Cooldown.get_active_cooldown(self.user_id)
    
    def is_in_cooldown(self):
        """Check if user is currently in cooldown"""
        return self.get_active_cooldown() is not None
    
    def trigger_cooldown(self, emotion, reason=None):
        """
        Trigger a cooldown based on emotion.
        
        Args:
            emotion: The dangerous emotion that triggered this
            reason: Optional additional context
            
        Returns:
            Cooldown: The created cooldown object
        """
        if not should_trigger_cooldown(emotion):
            return None
        
        duration = get_cooldown_duration(emotion)
        
        return Cooldown.create_cooldown(
            user_id=self.user_id,
            emotion=emotion,
            duration_minutes=duration,
            reason=reason or f"Detected dangerous emotion: {emotion}"
        )
    
    def check_and_trigger(self, emotion, trade_plan=None):
        """
        Check emotion and trigger cooldown if needed.
        
        Args:
            emotion: The current emotion
            trade_plan: Optional TradePlan object for context
            
        Returns:
            Cooldown or None
        """
        if not should_trigger_cooldown(emotion):
            return None
        
        # Build reason from context
        reason = f"Emotion '{emotion}' detected"
        if trade_plan:
            reason += f" during trade planning"
        
        return self.trigger_cooldown(emotion, reason)
    
    def override_cooldown(self, reason="User chose to continue"):
        """
        Override active cooldown (emergency bypass).
        This is logged for accountability.
        """
        cooldown = self.get_active_cooldown()
        if cooldown:
            cooldown.override(reason)
            return True
        return False

    def can_override_now(
        self,
        *,
        max_per_day: int = 1,
        max_per_week: int = 3,
        window_days: int = 7,
    ) -> bool:
        """
        Limit override frequency so users can't spam bypasses.

        Rules:
        - max_per_day: max overrides in the last 24 hours
        - max_per_week: max overrides in the last `window_days` days (default 7)
        """
        now = datetime.utcnow()
        cutoff_day = now - timedelta(hours=24)
        cutoff_week = now - timedelta(days=window_days)

        q = Cooldown.query.filter(
            Cooldown.user_id == self.user_id,
            Cooldown.was_overridden == True,
            Cooldown.started_at >= cutoff_week,
        )

        recent_day = q.filter(Cooldown.started_at >= cutoff_day).count()
        if recent_day >= max_per_day:
            return False

        recent_week = q.count()
        if recent_week >= max_per_week:
            return False

        return True

    def should_trigger_loss_streak(self, *, losses: int = 2, lookback_days: int = 14) -> bool:
        """
        Trigger cooldown if the most recent N CLOSED trades are all losses.
        Uses exit_date for ordering and requires profit_loss values.
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        recent = (
            Trade.query.filter(
                Trade.user_id == self.user_id,
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
                Trade.exit_date.isnot(None),
                Trade.exit_date >= cutoff,
            )
            .order_by(Trade.exit_date.desc())
            .limit(max(2, int(losses)))
            .all()
        )
        if len(recent) < losses:
            return False
        return all((t.profit_loss or 0) < 0 for t in recent[:losses])

    def trigger_loss_streak_cooldown(self, *, losses: int = 2, duration_minutes: int = 45) -> Cooldown | None:
        """
        Create a cooldown due to a loss streak (even if no 'emotion' was set).
        """
        if self.get_active_cooldown():
            return None
        if not self.should_trigger_loss_streak(losses=losses):
            return None
        return Cooldown.create_cooldown(
            user_id=self.user_id,
            emotion="Loss streak",
            duration_minutes=duration_minutes,
            reason=f"{losses} consecutive losses detected",
        )
    
    def get_cooldown_history(self, limit=10):
        """Get recent cooldown history for user"""
        return Cooldown.query.filter_by(
            user_id=self.user_id
        ).order_by(Cooldown.started_at.desc()).limit(limit).all()
    
    def get_cooldown_stats(self):
        """Get cooldown statistics for user"""
        all_cooldowns = Cooldown.query.filter_by(user_id=self.user_id).all()
        
        if not all_cooldowns:
            return {
                'total_cooldowns': 0,
                'total_overrides': 0,
                'most_common_trigger': None,
                'override_rate': 0
            }
        
        overrides = [c for c in all_cooldowns if c.was_overridden]
        
        # Count triggers by emotion
        emotion_counts = {}
        for c in all_cooldowns:
            emotion_counts[c.trigger_emotion] = emotion_counts.get(c.trigger_emotion, 0) + 1
        
        most_common = max(emotion_counts.items(), key=lambda x: x[1])[0] if emotion_counts else None
        
        return {
            'total_cooldowns': len(all_cooldowns),
            'total_overrides': len(overrides),
            'most_common_trigger': most_common,
            'override_rate': (len(overrides) / len(all_cooldowns) * 100) if all_cooldowns else 0,
            'emotion_breakdown': emotion_counts
        }


def check_cooldown(user_id):
    """Convenience function to check if user is in cooldown"""
    manager = CooldownManager(user_id)
    return manager.is_in_cooldown()


def get_active_cooldown(user_id):
    """Convenience function to get active cooldown"""
    return Cooldown.get_active_cooldown(user_id)


def trigger_emotional_cooldown(user_id, emotion, reason=None):
    """Convenience function to trigger cooldown"""
    manager = CooldownManager(user_id)
    return manager.trigger_cooldown(emotion, reason)
