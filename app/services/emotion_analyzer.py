"""
Emotion Analyzer
Analyzes emotional patterns in trading and their impact on performance
"""

from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from collections import defaultdict
from datetime import datetime, timedelta


class EmotionAnalyzer:
    """
    Analyzes emotional trading patterns.
    
    Provides insights on:
    - Most profitable emotions
    - Most dangerous emotions
    - Emotion frequency
    - Before vs after emotion changes
    - Emotion trends over time
    """
    
    # Emotion categories
    POSITIVE_EMOTIONS = ['Confident', 'Calm & Focused', 'Disciplined', 'Patient', 'Excited']
    NEGATIVE_EMOTIONS = ['FOMO', 'Revenge Trading', 'Greedy', 'Angry', 'Frustrated', 'Anxious', 'Fearful', 'Tired', 'Bored']
    NEUTRAL_EMOTIONS = ['Neutral', 'Nervous']
    
    # Emotion colors for charts
    EMOTION_COLORS = {
        'Confident': '#10b981',
        'Calm & Focused': '#059669',
        'Disciplined': '#047857',
        'Patient': '#0d9488',
        'Excited': '#14b8a6',
        'Neutral': '#6b7280',
        'Nervous': '#9ca3af',
        'FOMO': '#ef4444',
        'Revenge Trading': '#dc2626',
        'Greedy': '#f59e0b',
        'Angry': '#b91c1c',
        'Frustrated': '#ea580c',
        'Anxious': '#f97316',
        'Fearful': '#fb923c',
        'Tired': '#78716c',
        'Bored': '#a8a29e'
    }
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.trades = []
        self.plans = []
    
    def _load_data(self, days=90):
        """Load trades and plans for analysis"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        self.trades = Trade.query.filter(
            Trade.user_id == self.user_id,
            Trade.status == 'CLOSED',
            Trade.profit_loss.isnot(None),
            Trade.entry_date >= cutoff
        ).all()
        
        trade_ids = [t.id for t in self.trades]
        if trade_ids:
            self.plans = TradePlan.query.filter(
                TradePlan.trade_id.in_(trade_ids)
            ).all()
        
        return self.trades
    
    def get_emotion_performance(self, days=90):
        """
        Get performance breakdown by emotion.
        
        Returns:
            dict: Emotion -> {count, wins, losses, win_rate, total_pnl, avg_pnl}
        """
        self._load_data(days)
        
        emotion_stats = defaultdict(lambda: {
            'count': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'trades': []
        })
        
        for trade in self.trades:
            emotion = trade.emotion
            if not emotion:
                continue
            
            stats = emotion_stats[emotion]
            stats['count'] += 1
            stats['total_pnl'] += trade.profit_loss
            stats['trades'].append(trade)
            
            if trade.profit_loss > 0:
                stats['wins'] += 1
            else:
                stats['losses'] += 1
        
        # Calculate averages and win rates
        for emotion, stats in emotion_stats.items():
            if stats['count'] > 0:
                stats['win_rate'] = (stats['wins'] / stats['count']) * 100
                stats['avg_pnl'] = stats['total_pnl'] / stats['count']
            
            # Remove trades list to keep response clean
            del stats['trades']
        
        return dict(emotion_stats)
    
    def get_most_profitable_emotions(self, days=90, limit=5):
        """Get emotions ranked by profitability"""
        stats = self.get_emotion_performance(days)
        
        # Sort by total P/L
        sorted_emotions = sorted(
            stats.items(),
            key=lambda x: x[1]['total_pnl'],
            reverse=True
        )
        
        return sorted_emotions[:limit]
    
    def get_most_dangerous_emotions(self, days=90, limit=5):
        """Get emotions ranked by losses"""
        stats = self.get_emotion_performance(days)
        
        # Sort by total P/L (ascending for losses)
        sorted_emotions = sorted(
            stats.items(),
            key=lambda x: x[1]['total_pnl']
        )
        
        # Only return those with negative P/L
        dangerous = [(e, s) for e, s in sorted_emotions if s['total_pnl'] < 0]
        
        return dangerous[:limit]
    
    def get_emotion_frequency(self, days=90):
        """Get how often each emotion is reported"""
        stats = self.get_emotion_performance(days)
        
        frequency = {
            emotion: data['count']
            for emotion, data in stats.items()
        }
        
        return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True))
    
    def get_before_after_comparison(self, days=90):
        """
        Compare emotions before and after trades from trade plans.
        
        Returns insights on emotional changes.
        """
        self._load_data(days)
        
        comparisons = []
        
        for plan in self.plans:
            if plan.emotion_before and plan.emotion_after and plan.trade:
                comparisons.append({
                    'before': plan.emotion_before,
                    'after': plan.emotion_after,
                    'result': 'Win' if plan.trade.profit_loss > 0 else 'Loss',
                    'pnl': plan.trade.profit_loss
                })
        
        # Analyze patterns
        improved = 0  # Went from negative to positive
        worsened = 0  # Went from positive to negative
        stable = 0
        
        for comp in comparisons:
            before_positive = comp['before'] in self.POSITIVE_EMOTIONS
            after_positive = comp['after'] in self.POSITIVE_EMOTIONS
            
            if not before_positive and after_positive:
                improved += 1
            elif before_positive and not after_positive:
                worsened += 1
            else:
                stable += 1
        
        return {
            'comparisons': comparisons,
            'improved': improved,
            'worsened': worsened,
            'stable': stable,
            'total': len(comparisons)
        }
    
    def get_emotion_trend(self, days=90):
        """
        Get emotion trends over time (weekly breakdown).
        """
        self._load_data(days)
        
        # Group by week
        weekly_emotions = defaultdict(lambda: defaultdict(int))
        
        for trade in self.trades:
            if trade.emotion and trade.entry_date:
                week = trade.entry_date.strftime('%Y-W%W')
                weekly_emotions[week][trade.emotion] += 1
        
        # Convert to list format for charts
        trend_data = []
        for week in sorted(weekly_emotions.keys()):
            week_data = {'week': week}
            week_data.update(weekly_emotions[week])
            trend_data.append(week_data)
        
        return trend_data
    
    def get_chart_data(self, days=90):
        """
        Get all data formatted for Chart.js charts.
        """
        stats = self.get_emotion_performance(days)
        
        # Prepare data for different chart types
        emotions = list(stats.keys())
        
        return {
            'labels': emotions,
            'win_rates': [stats[e]['win_rate'] for e in emotions],
            'total_pnl': [stats[e]['total_pnl'] for e in emotions],
            'counts': [stats[e]['count'] for e in emotions],
            'colors': [self.EMOTION_COLORS.get(e, '#6b7280') for e in emotions],
            'avg_pnl': [stats[e]['avg_pnl'] for e in emotions]
        }
    
    def get_summary(self, days=90):
        """Get a summary of emotional trading patterns"""
        stats = self.get_emotion_performance(days)
        
        if not stats:
            return {
                'total_trades_with_emotion': 0,
                'most_common_emotion': None,
                'best_emotion': None,
                'worst_emotion': None,
                'recommendation': 'Log more trades with emotions to get insights.'
            }
        
        # Most common
        most_common = max(stats.items(), key=lambda x: x[1]['count'])
        
        # Best performer (by win rate, min 3 trades)
        qualified = {e: s for e, s in stats.items() if s['count'] >= 3}
        best = max(qualified.items(), key=lambda x: x[1]['win_rate']) if qualified else (None, None)
        
        # Worst performer
        worst = min(qualified.items(), key=lambda x: x[1]['win_rate']) if qualified else (None, None)
        
        # Generate recommendation
        if best[0] and worst[0]:
            recommendation = f"Trade more when feeling '{best[0]}' ({best[1]['win_rate']:.0f}% win rate). Avoid trading when '{worst[0]}' ({worst[1]['win_rate']:.0f}% win rate)."
        else:
            recommendation = "Need more data to provide recommendations."
        
        return {
            'total_trades_with_emotion': sum(s['count'] for s in stats.values()),
            'most_common_emotion': most_common[0],
            'most_common_count': most_common[1]['count'],
            'best_emotion': best[0],
            'best_win_rate': best[1]['win_rate'] if best[1] else 0,
            'worst_emotion': worst[0],
            'worst_win_rate': worst[1]['win_rate'] if worst[1] else 0,
            'recommendation': recommendation
        }


def analyze_emotions(user_id, days=90):
    """Convenience function to get emotion analysis"""
    analyzer = EmotionAnalyzer(user_id)
    return {
        'performance': analyzer.get_emotion_performance(days),
        'profitable': analyzer.get_most_profitable_emotions(days),
        'dangerous': analyzer.get_most_dangerous_emotions(days),
        'summary': analyzer.get_summary(days)
    }
