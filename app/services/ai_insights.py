"""
AI Insights Service
Builds advanced performance and behavioral insights from real trade data.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from sqlalchemy import or_, func

from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.services.emotion_analyzer import EmotionAnalyzer
from app.services.performance_calculator import PerformanceCalculator


class AIAnalyzer:
    """Generates AI-style trading insights from journal and plan data."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.now = datetime.now(timezone.utc)
        self.trades = []
        self.closed_trades = []
        self.plans = []

    def _load_trades(self, days: int = 90) -> List[Trade]:
        cutoff = self.now - timedelta(days=days)
        self.trades = Trade.query.filter(
            Trade.user_id == self.user_id,
            Trade.entry_date >= cutoff
        ).order_by(Trade.entry_date).all()

        self.closed_trades = [t for t in self.trades if t.status == 'CLOSED' and t.profit_loss is not None]
        self._load_plans()
        return self.trades

    def _load_plans(self) -> None:
        trade_ids = [trade.id for trade in self.trades]
        if not trade_ids:
            self.plans = []
            return
        self.plans = TradePlan.query.filter(
            or_(TradePlan.executed_trade_id.in_(trade_ids), TradePlan.trade_id.in_(trade_ids))
        ).all()

    def _trade_stats(self, trades: List[Trade]) -> Dict[str, Any]:
        stats = {
            'total_trades': len(trades),
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_rr': 0.0,
            'best_trade': None,
            'worst_trade': None,
        }
        if not trades:
            return stats

        wins = [t for t in trades if t.profit_loss and t.profit_loss > 0]
        losses = [t for t in trades if t.profit_loss and t.profit_loss < 0]
        pnl_values = [t.profit_loss or 0.0 for t in trades]
        rr_values = [t.risk_reward for t in trades if t.risk_reward is not None]

        stats['wins'] = len(wins)
        stats['losses'] = len(losses)
        stats['win_rate'] = (len(wins) / len(trades) * 100) if trades else 0.0
        stats['total_pnl'] = sum(pnl_values)
        stats['avg_win'] = sum((t.profit_loss for t in wins)) / len(wins) if wins else 0.0
        stats['avg_loss'] = abs(sum((t.profit_loss for t in losses))) / len(losses) if losses else 0.0
        stats['avg_rr'] = sum(rr_values) / len(rr_values) if rr_values else 0.0
        stats['best_trade'] = max(trades, key=lambda t: t.profit_loss or 0)
        stats['worst_trade'] = min(trades, key=lambda t: t.profit_loss or 0)
        return stats

    def _group_by_field(self, trades: List[Trade], field: str, min_count: int = 3):
        groups = defaultdict(list)
        for trade in trades:
            value = getattr(trade, field, None)
            if value:
                groups[value].append(trade)

        grouped = {}
        for key, items in groups.items():
            if len(items) >= min_count:
                grouped[key] = self._trade_stats(items)
        return grouped

    def _best_setup(self, trades: List[Trade]) -> Dict[str, Any]:
        strategy_stats = self._group_by_field(trades, 'strategy', min_count=3)
        instrument_stats = self._group_by_field(trades, 'symbol', min_count=3)
        emotion_stats = self._group_by_field(trades, 'emotion', min_count=3)

        result = {
            'best_strategy': None,
            'best_instrument': None,
            'best_emotion': None,
            'worst_strategy': None,
            'worst_instrument': None,
            'worst_emotion': None
        }

        if strategy_stats:
            best = max(strategy_stats.items(), key=lambda x: x[1]['win_rate'])
            worst = min(strategy_stats.items(), key=lambda x: x[1]['win_rate'])
            result['best_strategy'] = {'name': best[0], **best[1]}
            result['worst_strategy'] = {'name': worst[0], **worst[1]}

        if instrument_stats:
            best = max(instrument_stats.items(), key=lambda x: x[1]['win_rate'])
            worst = min(instrument_stats.items(), key=lambda x: x[1]['win_rate'])
            result['best_instrument'] = {'name': best[0], **best[1]}
            result['worst_instrument'] = {'name': worst[0], **worst[1]}

        if emotion_stats:
            best = max(emotion_stats.items(), key=lambda x: x[1]['win_rate'])
            worst = min(emotion_stats.items(), key=lambda x: x[1]['win_rate'])
            result['best_emotion'] = {'name': best[0], **best[1]}
            result['worst_emotion'] = {'name': worst[0], **worst[1]}

        return result

    def _best_day(self, trades: List[Trade]) -> Dict[str, Any]:
        by_day = defaultdict(list)
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for trade in trades:
            if trade.entry_date:
                by_day[trade.entry_date.weekday()].append(trade)

        filtered = {day: self._trade_stats(items) for day, items in by_day.items() if len(items) >= 3}
        if not filtered:
            return {}

        best_record = max(filtered.items(), key=lambda x: x[1]['win_rate'])
        worst_record = min(filtered.items(), key=lambda x: x[1]['win_rate'])
        return {
            'best_day': {'name': day_names[best_record[0]], **best_record[1]},
            'worst_day': {'name': day_names[worst_record[0]], **worst_record[1]}
        }

    def _build_strengths_weaknesses(self, stats: Dict[str, Any]) -> Dict[str, List[str]]:
        strengths = []
        weaknesses = []

        if stats['win_rate'] >= 55 and stats['total_trades'] >= 3:
            strengths.append('Your win rate is strong for the current sample.')
        if stats['avg_rr'] >= 2:
            strengths.append('Good risk-reward ratio on average.')
        if stats['total_pnl'] > 0:
            strengths.append('You are trading profitably overall.')
        if stats['win_rate'] < 45:
            weaknesses.append('Your win rate is lower than the ideal 50% threshold.')
        if stats['avg_rr'] < 1.5:
            weaknesses.append('Average reward relative to risk is weak.')
        if stats['total_pnl'] < 0:
            weaknesses.append('Your net result is negative. Review losing setups.')

        return {'strengths': strengths, 'weaknesses': weaknesses}

    def _detect_overtrading(self, trades: List[Trade]) -> bool:
        window = 7
        cutoff = self.now - timedelta(days=window)
        recent = [t for t in trades if t.entry_date and t.entry_date >= cutoff]
        return len(recent) >= 10

    def _detect_revenge_trading(self, trades: List[Trade]) -> bool:
        losses = []
        prev_loss = False
        for trade in sorted(trades, key=lambda t: t.entry_date or datetime.min):
            if prev_loss:
                losses.append(trade)
            prev_loss = trade.profit_loss is not None and trade.profit_loss < 0
        if not losses:
            return False
        loss_rate = len([t for t in losses if t.profit_loss and t.profit_loss < 0]) / len(losses) * 100
        return loss_rate > 50 and len(losses) >= 3

    def _get_risk_issues(self, trades: List[Trade]) -> List[str]:
        issues = []
        high_risk_trades = [t for t in trades if t.risk_percentage and t.risk_percentage > 2]
        low_rr_trades = [t for t in trades if t.risk_reward is not None and t.risk_reward < 1]
        missing_stop_loss = [t for t in trades if not t.stop_loss]

        if high_risk_trades:
            issues.append(f'{len(high_risk_trades)} trade(s) risked more than 2% of account.')
        if low_rr_trades:
            issues.append(f'{len(low_rr_trades)} trade(s) had R:R below 1:1.')
        if missing_stop_loss:
            issues.append(f'{len(missing_stop_loss)} trade(s) had no stop loss.')
        return issues

    def _get_mood_issues(self, trades: List[Trade]) -> List[str]:
        detector = EmotionAnalyzer(self.user_id)
        performance = detector.get_emotion_performance(days=90)
        issues = []
        for emotion, data in performance.items():
            if emotion in EmotionAnalyzer.NEGATIVE_EMOTIONS and data['win_rate'] < 50:
                issues.append(f'{emotion} trades win only {data["win_rate"]:.0f}% of the time.')
        return issues

    def get_weekly_review(self) -> Dict[str, Any]:
        self._load_trades(days=30)
        week_cutoff = self.now - timedelta(days=7)
        weekly_trades = [t for t in self.closed_trades if t.exit_date and t.exit_date >= week_cutoff]
        stats = self._trade_stats(weekly_trades)
        setups = self._best_setup(weekly_trades)
        day_insights = self._best_day(weekly_trades)
        alerts = []

        if self._detect_overtrading(self.trades):
            alerts.append('Overtrading detected: too many trades in the last 7 days.')
        if self._detect_revenge_trading(weekly_trades):
            alerts.append('Revenge trading pattern detected after losses.')
        alerts.extend(self._get_risk_issues(weekly_trades))
        alerts.extend(self._get_mood_issues(weekly_trades))

        strengths_weaknesses = self._build_strengths_weaknesses(stats)
        summary_text = self._build_summary_text(stats, setups, day_insights)

        return {
            'label': 'Weekly AI Review',
            'period': 'Last 7 days',
            'stats': stats,
            'setups': setups,
            'day_insights': day_insights,
            'alerts': alerts,
            'strengths': strengths_weaknesses['strengths'],
            'weaknesses': strengths_weaknesses['weaknesses'],
            'recommendations': self._get_recommendations(stats, setups),
            'summary': summary_text
        }

    def get_monthly_review(self) -> Dict[str, Any]:
        self._load_trades(days=90)
        month_cutoff = self.now - timedelta(days=30)
        monthly_trades = [t for t in self.closed_trades if t.exit_date and t.exit_date >= month_cutoff]
        stats = self._trade_stats(monthly_trades)
        direction = 'improving' if stats['total_trades'] and stats['win_rate'] >= 50 else 'needs review'
        return {
            'label': 'Monthly AI Review',
            'period': 'Last 30 days',
            'stats': stats,
            'direction': direction,
            'summary': f"Your last 30-day performance is {direction} with {stats['win_rate']:.0f}% wins and ${stats['total_pnl']:.2f} P/L."
        }

    def get_behavioral_insights(self) -> Dict[str, Any]:
        self._load_trades(days=90)
        score = PerformanceCalculator(self.user_id).calculate()
        negative_emotions = [t for t in self.trades if t.emotion in EmotionAnalyzer.NEGATIVE_EMOTIONS]
        positive_emotions = [t for t in self.trades if t.emotion in EmotionAnalyzer.POSITIVE_EMOTIONS]
        confidence_values = [t.confidence_level for t in self.trades if t.confidence_level is not None]

        return {
            'discipline_score': round(score.discipline_score or 0, 1),
            'consistency_score': round(score.consistency_score or 0, 1),
            'emotional_bias': f"{len(negative_emotions)} emotional trades in last 90 days",
            'confidence_trend': round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else None,
            'risk_behavior': {
                'avg_rr': round(sum((t.risk_reward or 0) for t in self.trades) / max(1, len([t for t in self.trades if t.risk_reward is not None])), 2) if self.trades else 0,
                'high_risk_trades': len([t for t in self.trades if t.risk_percentage and t.risk_percentage > 2])
            }
        }

    def _build_summary_text(self, stats: Dict[str, Any], setups: Dict[str, Any], day_insights: Dict[str, Any]) -> str:
        if stats['total_trades'] == 0:
            return 'No closed trades recorded this week. Log trades to get AI insights.'

        intro = f"This week you took {stats['total_trades']} closed trades with a {stats['win_rate']:.0f}% win rate and ${stats['total_pnl']:.2f} P/L."
        if setups.get('best_strategy'):
            intro += f" Your best strategy was {setups['best_strategy']['name']} with a {setups['best_strategy']['win_rate']:.0f}% win rate."
        if day_insights.get('best_day'):
            intro += f" Your strongest day was {day_insights['best_day']['name']} with a {day_insights['best_day']['win_rate']:.0f}% win rate."
        return intro

    def _get_recommendations(self, stats: Dict[str, Any], setups: Dict[str, Any]) -> List[str]:
        recommendations = []
        if stats['win_rate'] < 50:
            recommendations.append('Review your losing setups and avoid weak sessions.')
        if stats['avg_rr'] < 1.5:
            recommendations.append('Improve risk management by targeting R:R above 1.5:1.')
        if stats['total_pnl'] < 0:
            recommendations.append('Focus on quality setups and avoid emotional entries.')
        if setups.get('best_strategy'):
            recommendations.append(f'Trade more with {setups["best_strategy"]["name"]} when conditions are aligned.')
        if setups.get('worst_strategy') and setups['worst_strategy']['win_rate'] < 40:
            recommendations.append(f'Avoid {setups["worst_strategy"]["name"]} until you review the edge.')
        return recommendations

    def get_voice_summary(self) -> str:
        review = self.get_weekly_review()
        return (
            f"Hello trader, this week you took {review['stats']['total_trades']} closed trades. "
            f"Your win rate was {review['stats']['win_rate']:.0f} percent. "
            f"Your biggest strength was {review['setups'].get('best_strategy', {}).get('name', 'your strongest strategy')}. "
            f"Your biggest opportunity is to improve your risk reward and reduce emotional trades."
        )

    def answer_question(self, question: str) -> str:
        if not question:
            return 'Ask me anything about your recent trading performance.'

        text = question.strip().lower()
        weekly = self.get_weekly_review()
        behavioral = self.get_behavioral_insights()

        if 'perform' in text and 'week' in text:
            return weekly['summary']
        if 'mistake' in text or 'mistakes' in text:
            issues = weekly['alerts'][:3]
            return ' '.join(issues) if issues else 'Your biggest mistakes are low R:R and emotional trade entries. Review your recent losing trades.'
        if 'best setup' in text:
            best = weekly['setups'].get('best_strategy')
            return f"Your best setup is {best['name']} with a {best['win_rate']:.0f}% win rate." if best else 'You do not have a clear best setup yet.'
        if 'improve' in text:
            return ' '.join(weekly['recommendations'] or ['Focus on rule-based entries, stronger risk management, and better emotional control.'])
        if 'why' in text and 'losing' in text:
            if weekly['stats']['total_pnl'] < 0:
                return 'You are losing because your average R:R is low and you are trading during weak sessions or emotional states. Improve risk control and avoid revenge trades.'
            return 'Your losses are likely due to occasional weak setups or poor plan adherence. Review your trade notes and stop-loss discipline.'

        return weekly['summary']


def get_ai_insights(user_id: int) -> Dict[str, Any]:
    analyzer = AIAnalyzer(user_id)
    return {
        'weekly_review': analyzer.get_weekly_review(),
        'monthly_review': analyzer.get_monthly_review(),
        'behavioral_insights': analyzer.get_behavioral_insights(),
        'voice_summary': analyzer.get_voice_summary()
    }
