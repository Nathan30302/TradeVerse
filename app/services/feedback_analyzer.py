"""
AI Trade Feedback Analyzer
Analyzes trades and generates intelligent feedback based on rules and patterns
"""

from app import db
from app.models.trade_feedback import TradeFeedback


class FeedbackAnalyzer:
    """
    Analyzes trade data and generates automated feedback.
    Checks for rule violations, plan adherence, emotional trading, and more.
    """
    
    # Dangerous emotions that typically lead to poor decisions
    DANGEROUS_EMOTIONS = ['FOMO', 'Revenge Trading', 'Greedy', 'Angry', 'Frustrated', 'Anxious']
    
    # Good emotions for trading
    POSITIVE_EMOTIONS = ['Confident', 'Calm & Focused', 'Disciplined', 'Patient']
    
    def __init__(self, trade):
        """
        Initialize analyzer with a trade object.
        
        Args:
            trade: Trade model instance to analyze
        """
        self.trade = trade
        self.plan = trade.plan if trade.has_plan() else None
        self.feedbacks = []
    
    def analyze(self):
        """
        Run all analysis checks and generate feedback.
        
        Returns:
            list: List of TradeFeedback objects
        """
        self.feedbacks = []
        
        # Run all analysis methods
        self._check_risk_management()
        self._check_risk_reward()
        self._check_stop_loss()
        self._check_emotional_state()
        self._check_plan_adherence()
        self._check_discipline()
        self._check_execution_quality()
        self._check_win_loss_pattern()
        
        return self.feedbacks
    
    def save_feedback(self):
        """
        Save all generated feedback to database.
        Clears existing feedback for this trade first.
        """
        # Remove existing feedback for this trade
        TradeFeedback.query.filter_by(trade_id=self.trade.id).delete()
        
        # Add new feedback
        for feedback in self.feedbacks:
            db.session.add(feedback)
        
        db.session.commit()
        return self.feedbacks
    
    def _add_feedback(self, feedback_type, category, message, impact_score=0, icon=None):
        """Helper to create and add feedback"""
        if icon is None:
            icon = TradeFeedback.get_icon_for_type(feedback_type)
        
        feedback = TradeFeedback(
            trade_id=self.trade.id,
            user_id=self.trade.user_id,
            feedback_type=feedback_type,
            category=category,
            message=message,
            icon=icon,
            impact_score=impact_score
        )
        self.feedbacks.append(feedback)
    
    # ==================== Analysis Methods ====================
    
    def _check_risk_management(self):
        """Check risk management rules"""
        # Check if risk percentage is too high
        if self.plan and self.plan.planned_risk_percentage:
            risk = self.plan.planned_risk_percentage
            if risk > 5:
                self._add_feedback(
                    'critical', 'risk',
                    f'🚨 DANGER: You risked {risk}% of your account! Max recommended is 2%.',
                    impact_score=-8,
                    icon='🚨'
                )
            elif risk > 2:
                self._add_feedback(
                    'warning', 'risk',
                    f'Risk of {risk}% is above the recommended 2% maximum.',
                    impact_score=-3,
                    icon='⚠️'
                )
            elif risk <= 1:
                self._add_feedback(
                    'positive', 'risk',
                    f'Excellent risk management! Only {risk}% risked.',
                    impact_score=5,
                    icon='💪'
                )
    
    def _check_risk_reward(self):
        """Check risk-reward ratio"""
        rr = self.trade.risk_reward or (self.plan.planned_rr_ratio if self.plan else None)
        
        if rr is not None:
            if rr < 1:
                self._add_feedback(
                    'critical', 'risk',
                    f'Poor R:R of 1:{rr:.2f}. You\'re risking more than potential reward!',
                    impact_score=-5,
                    icon='📉'
                )
            elif rr >= 2:
                self._add_feedback(
                    'positive', 'risk',
                    f'Great R:R of 1:{rr:.2f}! This is a quality setup.',
                    impact_score=5,
                    icon='🎯'
                )
            elif rr >= 1.5:
                self._add_feedback(
                    'positive', 'risk',
                    f'Good R:R of 1:{rr:.2f}.',
                    impact_score=2,
                    icon='👍'
                )
    
    def _check_stop_loss(self):
        """Check stop loss usage"""
        if not self.trade.stop_loss:
            self._add_feedback(
                'critical', 'risk',
                'No stop loss set! This is extremely risky and can blow your account.',
                impact_score=-10,
                icon='💀'
            )
        elif self.plan and self.plan.moved_stop_loss:
            self._add_feedback(
                'critical', 'discipline',
                'You moved your stop loss! This is one of the worst trading habits.',
                impact_score=-8,
                icon='🚫'
            )
        elif self.plan and self.plan.followed_stop_loss:
            self._add_feedback(
                'positive', 'discipline',
                'You respected your stop loss. Great discipline!',
                impact_score=5,
                icon='🛡️'
            )
    
    def _check_emotional_state(self):
        """Check for emotional trading"""
        emotion = self.trade.emotion or (self.plan.emotion_before if self.plan else None)
        
        if emotion in self.DANGEROUS_EMOTIONS:
            self._add_feedback(
                'critical', 'emotion',
                f'You traded while feeling "{emotion}". This emotion leads to poor decisions.',
                impact_score=-6,
                icon='😰'
            )
            
            # Specific advice based on emotion
            if emotion == 'Revenge Trading':
                self._add_feedback(
                    'warning', 'emotion',
                    'Revenge trading often leads to bigger losses. Take a break after losses.',
                    impact_score=-3,
                    icon='⏸️'
                )
            elif emotion == 'FOMO':
                self._add_feedback(
                    'warning', 'emotion',
                    'FOMO trades rarely follow your plan. The market always offers new opportunities.',
                    impact_score=-3,
                    icon='🛑'
                )
            elif emotion == 'Greedy':
                self._add_feedback(
                    'warning', 'emotion',
                    'Greed can lead to oversizing or moving take profits. Stick to your plan.',
                    impact_score=-3,
                    icon='💸'
                )
        
        elif emotion in self.POSITIVE_EMOTIONS:
            self._add_feedback(
                'positive', 'emotion',
                f'Good mental state: "{emotion}". This is ideal for trading.',
                impact_score=4,
                icon='🧘'
            )
    
    def _check_plan_adherence(self):
        """Check if trader followed their plan"""
        if not self.plan:
            self._add_feedback(
                'warning', 'plan',
                'No trade plan created. Planning before trading improves discipline.',
                impact_score=-2,
                icon='📋'
            )
            return
        
        violations = 0
        
        if not self.plan.followed_entry:
            violations += 1
            self._add_feedback(
                'warning', 'execution',
                'You did not enter at your planned price.',
                impact_score=-2,
                icon='📍'
            )
        
        if not self.plan.followed_take_profit:
            violations += 1
            self._add_feedback(
                'warning', 'execution',
                'You did not take profit as planned.',
                impact_score=-2,
                icon='🎯'
            )
        
        if violations == 0 and self.plan.is_complete():
            self._add_feedback(
                'positive', 'plan',
                'Perfect execution! You followed your plan exactly.',
                impact_score=8,
                icon='🏆'
            )
    
    def _check_discipline(self):
        """Check overall discipline"""
        if self.trade.discipline_score is not None:
            score = self.trade.discipline_score
            if score >= 8:
                self._add_feedback(
                    'positive', 'discipline',
                    f'Excellent discipline score of {score}/10!',
                    impact_score=5,
                    icon='⭐'
                )
            elif score <= 4:
                self._add_feedback(
                    'warning', 'discipline',
                    f'Low discipline score of {score}/10. Review what went wrong.',
                    impact_score=-4,
                    icon='📉'
                )
        
        if not self.trade.checklist_completed:
            self._add_feedback(
                'warning', 'discipline',
                'Pre-trade checklist was not completed.',
                impact_score=-2,
                icon='📋'
            )
        
        if not self.trade.playbook_followed:
            self._add_feedback(
                'critical', 'discipline',
                'You did not follow your trading playbook!',
                impact_score=-5,
                icon='📖'
            )
    
    def _check_execution_quality(self):
        """Check execution quality"""
        if self.trade.execution_quality is not None:
            quality = self.trade.execution_quality
            if quality >= 4:
                self._add_feedback(
                    'positive', 'execution',
                    f'Good execution quality ({quality}/5 stars).',
                    impact_score=3,
                    icon='✨'
                )
            elif quality <= 2:
                self._add_feedback(
                    'warning', 'execution',
                    f'Poor execution quality ({quality}/5 stars). Practice your entries.',
                    impact_score=-2,
                    icon='🔧'
                )
    
    def _check_win_loss_pattern(self):
        """Check win/loss and provide context"""
        if self.trade.profit_loss is None:
            return
        
        if self.trade.is_winner():
            # Check if it was a good win or lucky
            if self.plan and self.plan.is_complete():
                if self.plan.followed_entry and self.plan.followed_stop_loss:
                    self._add_feedback(
                        'positive', 'execution',
                        'Quality win! You followed your plan and it paid off.',
                        impact_score=5,
                        icon='🎉'
                    )
                else:
                    self._add_feedback(
                        'warning', 'execution',
                        'You won, but didn\'t follow your plan. This could have been luck.',
                        impact_score=0,
                        icon='🍀'
                    )
            else:
                self._add_feedback(
                    'positive', 'execution',
                    'Winning trade! Great job.',
                    impact_score=3,
                    icon='💰'
                )
        
        elif self.trade.is_loser():
            if self.plan and self.plan.followed_stop_loss:
                self._add_feedback(
                    'positive', 'discipline',
                    'You lost, but you respected your stop loss. Losses are part of trading.',
                    impact_score=2,
                    icon='👏'
                )
            
            # Check if emotional trading caused the loss
            emotion = self.trade.emotion or (self.plan.emotion_before if self.plan else None)
            if emotion in self.DANGEROUS_EMOTIONS:
                self._add_feedback(
                    'critical', 'emotion',
                    f'This loss may have been caused by emotional trading ({emotion}).',
                    impact_score=-4,
                    icon='💔'
                )


def generate_trade_feedback(trade):
    """
    Convenience function to analyze a trade and save feedback.
    
    Args:
        trade: Trade model instance
        
    Returns:
        list: List of generated TradeFeedback objects
    """
    analyzer = FeedbackAnalyzer(trade)
    analyzer.analyze()
    return analyzer.save_feedback()
