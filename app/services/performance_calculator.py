"""
Performance Score Calculator
Calculates weekly performance scores based on trading metrics
"""

from app import db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.performance_score import PerformanceScore
from datetime import datetime, timedelta
from sqlalchemy import func


class PerformanceCalculator:
    """
    Calculates comprehensive weekly performance scores.
    
    Scoring Components:
    - Rule Compliance (25%): Stop loss usage, checklist, playbook
    - RR Quality (25%): Average risk-reward ratio
    - Emotional Score (20%): Trading with good emotions
    - Consistency (15%): Session/time consistency
    - Discipline (15%): Plan adherence, execution quality
    """
    
    # Dangerous emotions
    DANGEROUS_EMOTIONS = ['FOMO', 'Revenge Trading', 'Greedy', 'Angry', 'Frustrated', 'Anxious']
    POSITIVE_EMOTIONS = ['Confident', 'Calm & Focused', 'Disciplined', 'Patient']
    
    # Component weights (must sum to 1.0)
    WEIGHTS = {
        'rule_compliance': 0.25,
        'rr_quality': 0.25,
        'emotional': 0.20,
        'consistency': 0.15,
        'discipline': 0.15
    }
    
    def __init__(self, user_id, week_start=None):
        """
        Initialize calculator.
        
        Args:
            user_id: User to calculate score for
            week_start: Start date of week (defaults to current week)
        """
        self.user_id = user_id
        
        if week_start is None:
            # Get current week's Monday
            today = datetime.utcnow().date()
            self.week_start = today - timedelta(days=today.weekday())
        else:
            self.week_start = week_start
        
        self.week_end = self.week_start + timedelta(days=6)
        self.trades = []
        self.plans = []
    
    def _get_trades_for_week(self):
        """Fetch all trades for the week"""
        self.trades = Trade.query.filter(
            Trade.user_id == self.user_id,
            Trade.entry_date >= datetime.combine(self.week_start, datetime.min.time()),
            Trade.entry_date <= datetime.combine(self.week_end, datetime.max.time())
        ).all()
        
        # Get associated plans
        trade_ids = [t.id for t in self.trades]
        if trade_ids:
            self.plans = TradePlan.query.filter(TradePlan.trade_id.in_(trade_ids)).all()
        
        return self.trades
    
    def calculate(self):
        """
        Calculate all performance scores for the week.
        
        Returns:
            PerformanceScore: The calculated performance score object
        """
        self._get_trades_for_week()
        
        # If no trades, return empty score
        if not self.trades:
            return self._create_empty_score()
        
        # Calculate component scores
        rule_compliance = self._calculate_rule_compliance()
        rr_quality = self._calculate_rr_quality()
        emotional = self._calculate_emotional_score()
        consistency = self._calculate_consistency()
        discipline = self._calculate_discipline()
        
        # Calculate overall score (weighted average)
        overall = (
            rule_compliance * self.WEIGHTS['rule_compliance'] +
            rr_quality * self.WEIGHTS['rr_quality'] +
            emotional * self.WEIGHTS['emotional'] +
            consistency * self.WEIGHTS['consistency'] +
            discipline * self.WEIGHTS['discipline']
        )
        
        # Calculate trade stats
        closed_trades = [t for t in self.trades if t.status == 'CLOSED']
        winning = [t for t in closed_trades if t.profit_loss and t.profit_loss > 0]
        losing = [t for t in closed_trades if t.profit_loss and t.profit_loss < 0]
        
        win_rate = (len(winning) / len(closed_trades) * 100) if closed_trades else 0
        total_pnl = sum(t.profit_loss or 0 for t in closed_trades)
        
        rr_values = [t.risk_reward for t in self.trades if t.risk_reward]
        avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0
        
        # Create or update score
        score = PerformanceScore.query.filter_by(
            user_id=self.user_id,
            week_start=self.week_start
        ).first()
        
        if not score:
            score = PerformanceScore(
                user_id=self.user_id,
                week_start=self.week_start,
                week_end=self.week_end,
                week_number=self.week_start.isocalendar()[1],
                year=self.week_start.year
            )
        
        score.overall_score = overall
        score.grade = PerformanceScore.get_grade(overall)
        score.rule_compliance_score = rule_compliance
        score.rr_quality_score = rr_quality
        score.emotional_score = emotional
        score.consistency_score = consistency
        score.discipline_score = discipline
        score.total_trades = len(self.trades)
        score.winning_trades = len(winning)
        score.losing_trades = len(losing)
        score.win_rate = win_rate
        score.total_pnl = total_pnl
        score.avg_rr = avg_rr
        score.calculated_at = datetime.utcnow()
        
        return score
    
    def save(self):
        """Calculate and save score to database"""
        score = self.calculate()
        db.session.add(score)
        db.session.commit()
        return score
    
    def _create_empty_score(self):
        """Create an empty score for weeks with no trades"""
        return PerformanceScore(
            user_id=self.user_id,
            week_start=self.week_start,
            week_end=self.week_end,
            week_number=self.week_start.isocalendar()[1],
            year=self.week_start.year,
            overall_score=0,
            grade='N/A'
        )
    
    def _calculate_rule_compliance(self):
        """
        Calculate rule compliance score (0-100).
        Based on: stop loss usage, checklist completion, playbook adherence
        """
        if not self.trades:
            return 0
        
        total_points = 0
        max_points = len(self.trades) * 3  # 3 criteria per trade
        
        for trade in self.trades:
            # Stop loss set (+1)
            if trade.stop_loss:
                total_points += 1
            
            # Checklist completed (+1)
            if trade.checklist_completed:
                total_points += 1
            
            # Playbook followed (+1)
            if trade.playbook_followed:
                total_points += 1
        
        return (total_points / max_points * 100) if max_points > 0 else 0
    
    def _calculate_rr_quality(self):
        """
        Calculate R:R quality score (0-100).
        Score based on average risk-reward ratio.
        """
        rr_values = [t.risk_reward for t in self.trades if t.risk_reward]
        
        if not rr_values:
            return 50  # Neutral if no R:R data
        
        avg_rr = sum(rr_values) / len(rr_values)
        
        # Score calculation:
        # R:R >= 3.0 = 100
        # R:R >= 2.0 = 85
        # R:R >= 1.5 = 70
        # R:R >= 1.0 = 50
        # R:R < 1.0 = 30 or less
        
        if avg_rr >= 3.0:
            return 100
        elif avg_rr >= 2.0:
            return 85 + (avg_rr - 2.0) * 15
        elif avg_rr >= 1.5:
            return 70 + (avg_rr - 1.5) * 30
        elif avg_rr >= 1.0:
            return 50 + (avg_rr - 1.0) * 40
        else:
            return max(0, avg_rr * 50)
    
    def _calculate_emotional_score(self):
        """
        Calculate emotional trading score (0-100).
        Penalize dangerous emotions, reward positive ones.
        """
        if not self.trades:
            return 50
        
        score = 70  # Start neutral
        
        for trade in self.trades:
            emotion = trade.emotion
            
            if emotion in self.DANGEROUS_EMOTIONS:
                score -= 15  # Heavy penalty
            elif emotion in self.POSITIVE_EMOTIONS:
                score += 10  # Bonus
        
        # Also check plan emotions
        for plan in self.plans:
            if plan.emotion_before in self.DANGEROUS_EMOTIONS:
                score -= 10
            elif plan.emotion_before in self.POSITIVE_EMOTIONS:
                score += 5
        
        return max(0, min(100, score))
    
    def _calculate_consistency(self):
        """
        Calculate consistency score (0-100).
        Based on trading at consistent times/sessions.
        """
        if len(self.trades) < 2:
            return 50  # Not enough data
        
        # Check session consistency
        sessions = [t.session_type for t in self.trades if t.session_type]
        
        if not sessions:
            return 50
        
        # Calculate how consistent the sessions are
        session_counts = {}
        for s in sessions:
            session_counts[s] = session_counts.get(s, 0) + 1
        
        # Consistency = how much they stick to their main session
        max_session_count = max(session_counts.values())
        consistency_ratio = max_session_count / len(sessions)
        
        return consistency_ratio * 100
    
    def _calculate_discipline(self):
        """
        Calculate discipline score (0-100).
        Based on plan adherence and execution quality.
        """
        if not self.trades:
            return 50
        
        total_points = 0
        max_points = 0
        
        for trade in self.trades:
            # Discipline score from trade (if available)
            if trade.discipline_score is not None:
                total_points += trade.discipline_score * 10  # Scale to 100
                max_points += 100
            
            # Execution quality (if available)
            if trade.execution_quality is not None:
                total_points += trade.execution_quality * 20  # Scale to 100
                max_points += 100
        
        # Check plan adherence
        for plan in self.plans:
            if plan.is_complete():
                adherence_score = 0
                if plan.followed_entry:
                    adherence_score += 25
                if plan.followed_stop_loss:
                    adherence_score += 35
                if plan.followed_take_profit:
                    adherence_score += 25
                if not plan.moved_stop_loss:
                    adherence_score += 15
                
                total_points += adherence_score
                max_points += 100
        
        if max_points == 0:
            return 50  # Default if no data
        
        return (total_points / max_points * 100)


def calculate_weekly_score(user_id, week_start=None):
    """
    Convenience function to calculate and save weekly score.
    
    Args:
        user_id: User to calculate for
        week_start: Optional week start date
        
    Returns:
        PerformanceScore: The calculated and saved score
    """
    calculator = PerformanceCalculator(user_id, week_start)
    return calculator.save()


def get_performance_history(user_id, weeks=12):
    """
    Get performance score history for charts.
    
    Args:
        user_id: User to get history for
        weeks: Number of weeks to fetch
        
    Returns:
        list: List of PerformanceScore objects
    """
    return PerformanceScore.query.filter_by(
        user_id=user_id
    ).order_by(
        PerformanceScore.week_start.desc()
    ).limit(weeks).all()
