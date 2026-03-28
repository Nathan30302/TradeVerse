"""
Behavior Pattern Detector
Analyzes historical trades to discover trading patterns and insights
"""

from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from sqlalchemy import func
from collections import defaultdict
from datetime import datetime, timedelta


class PatternDetector:
    """
    Analyzes trade history to detect behavioral patterns.
    
    Patterns detected:
    - Best/worst trading sessions
    - Best/worst strategies
    - Emotional patterns (which emotions lead to wins/losses)
    - Day of week patterns
    - Time of day patterns
    - Setup type performance
    - Risk-reward correlations
    """
    
    # Minimum trades required for statistical significance
    MIN_TRADES_FOR_PATTERN = 3
    
    # Dangerous emotions
    DANGEROUS_EMOTIONS = ['FOMO', 'Revenge Trading', 'Greedy', 'Angry', 'Frustrated', 'Anxious', 'Tired', 'Bored']
    POSITIVE_EMOTIONS = ['Confident', 'Calm & Focused', 'Disciplined', 'Patient']
    
    def __init__(self, user_id):
        """
        Initialize pattern detector.
        
        Args:
            user_id: User to analyze patterns for
        """
        self.user_id = user_id
        self.trades = []
        self.patterns = []
    
    def _load_trades(self, days=90):
        """Load trades for analysis"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.trades = Trade.query.filter(
            Trade.user_id == self.user_id,
            Trade.status == 'CLOSED',
            Trade.profit_loss.isnot(None),
            Trade.entry_date >= cutoff
        ).all()
        return self.trades
    
    def analyze(self, days=90):
        """
        Run all pattern detection analyses.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            list: List of detected patterns
        """
        self._load_trades(days)
        self.patterns = []
        
        if len(self.trades) < self.MIN_TRADES_FOR_PATTERN:
            self.patterns.append({
                'type': 'info',
                'category': 'general',
                'icon': 'ℹ️',
                'title': 'Not Enough Data',
                'message': f'Need at least {self.MIN_TRADES_FOR_PATTERN} closed trades to detect patterns. You have {len(self.trades)}.',
                'confidence': 0
            })
            return self.patterns
        
        # Run all pattern detectors
        self._detect_session_patterns()
        self._detect_strategy_patterns()
        self._detect_emotion_patterns()
        self._detect_day_patterns()
        self._detect_instrument_patterns()
        self._detect_rr_patterns()
        self._detect_time_patterns()
        self._detect_streak_patterns()
        
        # Sort by confidence
        self.patterns.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        return self.patterns
    
    def _add_pattern(self, pattern_type, category, icon, title, message, confidence, data=None):
        """Helper to add a pattern"""
        self.patterns.append({
            'type': pattern_type,  # 'positive', 'warning', 'insight'
            'category': category,
            'icon': icon,
            'title': title,
            'message': message,
            'confidence': confidence,  # 0-100
            'data': data or {}
        })
    
    def _calculate_stats(self, trades):
        """Calculate win rate and avg P/L for a list of trades"""
        if not trades:
            return {'count': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0}
        
        wins = [t for t in trades if t.profit_loss > 0]
        total_pnl = sum(t.profit_loss for t in trades)
        
        return {
            'count': len(trades),
            'wins': len(wins),
            'losses': len(trades) - len(wins),
            'win_rate': len(wins) / len(trades) * 100,
            'avg_pnl': total_pnl / len(trades),
            'total_pnl': total_pnl
        }
    
    # ==================== Pattern Detection Methods ====================
    
    def _detect_session_patterns(self):
        """Detect best and worst trading sessions"""
        session_trades = defaultdict(list)
        
        for trade in self.trades:
            if trade.session_type:
                session_trades[trade.session_type].append(trade)
        
        if len(session_trades) < 2:
            return
        
        session_stats = {}
        for session, trades in session_trades.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                session_stats[session] = self._calculate_stats(trades)
        
        if not session_stats:
            return
        
        # Find best session
        best_session = max(session_stats.items(), key=lambda x: x[1]['win_rate'])
        worst_session = min(session_stats.items(), key=lambda x: x[1]['win_rate'])
        
        if best_session[1]['win_rate'] >= 60:
            self._add_pattern(
                'positive', 'session', '🌍',
                f'Best Session: {best_session[0]}',
                f'You win {best_session[1]["win_rate"]:.0f}% of trades during {best_session[0]} ({best_session[1]["count"]} trades).',
                confidence=min(95, 50 + best_session[1]['count'] * 2),
                data={'session': best_session[0], 'stats': best_session[1]}
            )
        
        if worst_session[1]['win_rate'] <= 40 and worst_session[0] != best_session[0]:
            self._add_pattern(
                'warning', 'session', '⚠️',
                f'Worst Session: {worst_session[0]}',
                f'Only {worst_session[1]["win_rate"]:.0f}% win rate during {worst_session[0]}. Consider avoiding this session.',
                confidence=min(90, 50 + worst_session[1]['count'] * 2),
                data={'session': worst_session[0], 'stats': worst_session[1]}
            )
    
    def _detect_strategy_patterns(self):
        """Detect best and worst strategies"""
        strategy_trades = defaultdict(list)
        
        for trade in self.trades:
            if trade.strategy:
                strategy_trades[trade.strategy].append(trade)
        
        if len(strategy_trades) < 2:
            return
        
        strategy_stats = {}
        for strategy, trades in strategy_trades.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                strategy_stats[strategy] = self._calculate_stats(trades)
        
        if not strategy_stats:
            return
        
        # Find best and worst
        best = max(strategy_stats.items(), key=lambda x: x[1]['win_rate'])
        worst = min(strategy_stats.items(), key=lambda x: x[1]['win_rate'])
        
        if best[1]['win_rate'] >= 55:
            self._add_pattern(
                'positive', 'strategy', '🎯',
                f'Best Strategy: {best[0]}',
                f'{best[0]} has {best[1]["win_rate"]:.0f}% win rate with ${best[1]["total_pnl"]:.2f} total P/L.',
                confidence=min(95, 50 + best[1]['count'] * 3),
                data={'strategy': best[0], 'stats': best[1]}
            )
        
        if worst[1]['win_rate'] <= 45 and worst[0] != best[0]:
            self._add_pattern(
                'warning', 'strategy', '📉',
                f'Weakest Strategy: {worst[0]}',
                f'{worst[0]} only has {worst[1]["win_rate"]:.0f}% win rate. Consider reviewing or dropping it.',
                confidence=min(90, 50 + worst[1]['count'] * 3),
                data={'strategy': worst[0], 'stats': worst[1]}
            )
    
    def _detect_emotion_patterns(self):
        """Detect emotional trading patterns"""
        emotion_trades = defaultdict(list)
        
        for trade in self.trades:
            if trade.emotion:
                emotion_trades[trade.emotion].append(trade)
        
        dangerous_stats = []
        positive_stats = []
        
        for emotion, trades in emotion_trades.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                stats = self._calculate_stats(trades)
                stats['emotion'] = emotion
                
                if emotion in self.DANGEROUS_EMOTIONS:
                    dangerous_stats.append(stats)
                elif emotion in self.POSITIVE_EMOTIONS:
                    positive_stats.append(stats)
        
        # Report dangerous emotions with losses
        for stats in dangerous_stats:
            if stats['win_rate'] < 50:
                self._add_pattern(
                    'warning', 'emotion', '😰',
                    f'Emotional Leak: {stats["emotion"]}',
                    f'When feeling {stats["emotion"]}, you only win {stats["win_rate"]:.0f}% ({stats["count"]} trades). This emotion is costing you money!',
                    confidence=min(95, 60 + stats['count'] * 4),
                    data=stats
                )
        
        # Report positive emotions with wins
        for stats in positive_stats:
            if stats['win_rate'] >= 55:
                self._add_pattern(
                    'positive', 'emotion', '🧘',
                    f'Best Emotional State: {stats["emotion"]}',
                    f'When {stats["emotion"]}, you win {stats["win_rate"]:.0f}% of trades. Trade more in this state!',
                    confidence=min(95, 55 + stats['count'] * 3),
                    data=stats
                )
    
    def _detect_day_patterns(self):
        """Detect day of week patterns"""
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_trades = defaultdict(list)
        
        for trade in self.trades:
            if trade.entry_date:
                day = trade.entry_date.weekday()
                day_trades[day].append(trade)
        
        day_stats = {}
        for day, trades in day_trades.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                day_stats[day] = self._calculate_stats(trades)
                day_stats[day]['day_name'] = day_names[day]
        
        if len(day_stats) < 2:
            return
        
        best_day = max(day_stats.items(), key=lambda x: x[1]['win_rate'])
        worst_day = min(day_stats.items(), key=lambda x: x[1]['win_rate'])
        
        if best_day[1]['win_rate'] >= 60:
            self._add_pattern(
                'positive', 'timing', '📅',
                f'Best Day: {best_day[1]["day_name"]}',
                f'{best_day[1]["day_name"]}s are your best with {best_day[1]["win_rate"]:.0f}% win rate.',
                confidence=min(85, 50 + best_day[1]['count'] * 2),
                data=best_day[1]
            )
        
        if worst_day[1]['win_rate'] <= 40 and worst_day[0] != best_day[0]:
            self._add_pattern(
                'warning', 'timing', '📅',
                f'Worst Day: {worst_day[1]["day_name"]}',
                f'Avoid trading on {worst_day[1]["day_name"]}s - only {worst_day[1]["win_rate"]:.0f}% win rate.',
                confidence=min(85, 50 + worst_day[1]['count'] * 2),
                data=worst_day[1]
            )
    
    def _detect_instrument_patterns(self):
        """Detect best and worst instruments"""
        instrument_trades = defaultdict(list)
        
        for trade in self.trades:
            instrument_trades[trade.symbol].append(trade)
        
        instrument_stats = {}
        for symbol, trades in instrument_trades.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                instrument_stats[symbol] = self._calculate_stats(trades)
        
        if len(instrument_stats) < 2:
            return
        
        best = max(instrument_stats.items(), key=lambda x: x[1]['win_rate'])
        worst = min(instrument_stats.items(), key=lambda x: x[1]['win_rate'])
        
        if best[1]['win_rate'] >= 60:
            self._add_pattern(
                'positive', 'instrument', '📊',
                f'Best Instrument: {best[0]}',
                f'{best[0]} is your strongest pair with {best[1]["win_rate"]:.0f}% win rate.',
                confidence=min(90, 50 + best[1]['count'] * 2),
                data={'symbol': best[0], 'stats': best[1]}
            )
        
        if worst[1]['win_rate'] <= 40 and worst[0] != best[0]:
            self._add_pattern(
                'warning', 'instrument', '📊',
                f'Weakest Instrument: {worst[0]}',
                f'{worst[0]} is hurting you with only {worst[1]["win_rate"]:.0f}% win rate. Consider removing it.',
                confidence=min(90, 50 + worst[1]['count'] * 2),
                data={'symbol': worst[0], 'stats': worst[1]}
            )
    
    def _detect_rr_patterns(self):
        """Detect risk-reward patterns"""
        high_rr_trades = [t for t in self.trades if t.risk_reward and t.risk_reward >= 2]
        low_rr_trades = [t for t in self.trades if t.risk_reward and t.risk_reward < 1]
        
        if len(high_rr_trades) >= self.MIN_TRADES_FOR_PATTERN:
            stats = self._calculate_stats(high_rr_trades)
            if stats['total_pnl'] > 0:
                self._add_pattern(
                    'positive', 'risk', '💰',
                    'High R:R Trades Are Profitable',
                    f'Trades with R:R ≥ 2 are profitable: {stats["win_rate"]:.0f}% win rate, ${stats["total_pnl"]:.2f} total.',
                    confidence=min(90, 55 + stats['count'] * 2),
                    data=stats
                )
        
        if len(low_rr_trades) >= self.MIN_TRADES_FOR_PATTERN:
            stats = self._calculate_stats(low_rr_trades)
            if stats['total_pnl'] < 0:
                self._add_pattern(
                    'warning', 'risk', '⚠️',
                    'Low R:R Trades Are Losing Money',
                    f'Trades with R:R < 1 are costing you: ${abs(stats["total_pnl"]):.2f} lost. Avoid these setups!',
                    confidence=min(90, 55 + stats['count'] * 2),
                    data=stats
                )
    
    def _detect_time_patterns(self):
        """Detect time of day patterns"""
        hour_trades = defaultdict(list)
        
        for trade in self.trades:
            if trade.entry_date:
                hour = trade.entry_date.hour
                hour_trades[hour].append(trade)
        
        # Group into time blocks
        morning = []  # 6-12
        afternoon = []  # 12-18
        evening = []  # 18-24
        night = []  # 0-6
        
        for hour, trades in hour_trades.items():
            if 6 <= hour < 12:
                morning.extend(trades)
            elif 12 <= hour < 18:
                afternoon.extend(trades)
            elif 18 <= hour < 24:
                evening.extend(trades)
            else:
                night.extend(trades)
        
        time_blocks = {
            'Morning (6AM-12PM)': morning,
            'Afternoon (12PM-6PM)': afternoon,
            'Evening (6PM-12AM)': evening,
            'Night (12AM-6AM)': night
        }
        
        time_stats = {}
        for block, trades in time_blocks.items():
            if len(trades) >= self.MIN_TRADES_FOR_PATTERN:
                time_stats[block] = self._calculate_stats(trades)
        
        if len(time_stats) >= 2:
            best = max(time_stats.items(), key=lambda x: x[1]['win_rate'])
            if best[1]['win_rate'] >= 55:
                self._add_pattern(
                    'insight', 'timing', '🕐',
                    f'Best Trading Time: {best[0]}',
                    f'You perform best during {best[0]} with {best[1]["win_rate"]:.0f}% win rate.',
                    confidence=min(80, 50 + best[1]['count']),
                    data=best[1]
                )
    
    def _detect_streak_patterns(self):
        """Detect patterns in winning/losing streaks"""
        # Sort trades by date
        sorted_trades = sorted(self.trades, key=lambda t: t.entry_date or datetime.min)
        
        if len(sorted_trades) < 5:
            return
        
        # Count trades after losses
        trades_after_loss = []
        prev_was_loss = False
        
        for trade in sorted_trades:
            if prev_was_loss:
                trades_after_loss.append(trade)
            prev_was_loss = trade.profit_loss < 0
        
        if len(trades_after_loss) >= self.MIN_TRADES_FOR_PATTERN:
            stats = self._calculate_stats(trades_after_loss)
            if stats['win_rate'] < 45:
                self._add_pattern(
                    'warning', 'behavior', '🔄',
                    'Revenge Trading Pattern Detected',
                    f'After a loss, your next trade only wins {stats["win_rate"]:.0f}% of the time. Consider taking a break after losses.',
                    confidence=min(85, 55 + stats['count'] * 2),
                    data=stats
                )
            elif stats['win_rate'] >= 55:
                self._add_pattern(
                    'positive', 'behavior', '💪',
                    'Good Recovery After Losses',
                    f'You bounce back well! {stats["win_rate"]:.0f}% win rate on trades after a loss.',
                    confidence=min(80, 50 + stats['count'] * 2),
                    data=stats
                )


def detect_patterns(user_id, days=90):
    """
    Convenience function to detect patterns.
    
    Args:
        user_id: User to analyze
        days: Number of days to look back
        
    Returns:
        list: Detected patterns
    """
    detector = PatternDetector(user_id)
    return detector.analyze(days)
