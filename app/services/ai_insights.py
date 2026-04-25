"""
AI Buddy Insights Service
Builds advanced performance and behavioral insights from real trade data.
All methods are defensively coded to return safe defaults when no trade data exists.
"""
 
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
 
from sqlalchemy import or_, func
 
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.services.emotion_analyzer import EmotionAnalyzer
from app.services.performance_calculator import PerformanceCalculator
 
 
# ---------------------------------------------------------------------------
# Shared empty-stats template — every caller gets a fully-populated dict even
# when there is no trade data, so templates never hit a KeyError / UndefinedError.
# ---------------------------------------------------------------------------
_EMPTY_STATS: Dict[str, Any] = {
    'total_trades': 0,
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
 
_EMPTY_SETUPS: Dict[str, Any] = {
    'best_strategy': None,
    'best_instrument': None,
    'best_emotion': None,
    'worst_strategy': None,
    'worst_instrument': None,
    'worst_emotion': None,
}
 
 
def _copy_empty_stats() -> Dict[str, Any]:
    return dict(_EMPTY_STATS)
 
 
def _copy_empty_setups() -> Dict[str, Any]:
    return dict(_EMPTY_SETUPS)
 
 
class AIAnalyzer:
    """Generates AI Buddy trading insights from journal and plan data."""
 
    def __init__(self, user_id: int):
        self.user_id = user_id
        # Use timezone-aware UTC now throughout so comparisons with aware
        # datetimes never raise TypeError.
        self.now = datetime.now(timezone.utc)
        self.trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.plans: List[TradePlan] = []
 
    # ------------------------------------------------------------------
    # Internal data loading
    # ------------------------------------------------------------------
 
    def _load_trades(self, days: int = 90) -> List[Trade]:
        """Load trades for the given look-back window.
 
        Handles both timezone-aware and timezone-naive entry_date values stored
        in the database by converting the cutoff to a naive UTC datetime when
        the DB column is naive, and keeping it aware otherwise.
        """
        cutoff_aware = self.now - timedelta(days=days)
        # Also prepare a naive version in case DB stores naive datetimes
        cutoff_naive = cutoff_aware.replace(tzinfo=None)
 
        try:
            # Try with timezone-aware cutoff first
            self.trades = Trade.query.filter(
                Trade.user_id == self.user_id,
                Trade.entry_date >= cutoff_aware
            ).order_by(Trade.entry_date).all()
        except Exception:
            # Fall back to naive comparison
            try:
                self.trades = Trade.query.filter(
                    Trade.user_id == self.user_id,
                    Trade.entry_date >= cutoff_naive
                ).order_by(Trade.entry_date).all()
            except Exception:
                self.trades = []
 
        self.closed_trades = [
            t for t in self.trades
            if t.status == 'CLOSED' and t.profit_loss is not None
        ]
        self._load_plans()
        return self.trades
 
    def _load_plans(self) -> None:
        trade_ids = [trade.id for trade in self.trades]
        if not trade_ids:
            self.plans = []
            return
        try:
            self.plans = TradePlan.query.filter(
                or_(
                    TradePlan.executed_trade_id.in_(trade_ids),
                    TradePlan.trade_id.in_(trade_ids)
                )
            ).all()
        except Exception:
            self.plans = []
 
    # ------------------------------------------------------------------
    # Stats helpers
    # ------------------------------------------------------------------
 
    def _trade_stats(self, trades: List[Trade]) -> Dict[str, Any]:
        stats = _copy_empty_stats()
        if not trades:
            return stats
 
        wins = [t for t in trades if t.profit_loss and t.profit_loss > 0]
        losses = [t for t in trades if t.profit_loss and t.profit_loss < 0]
        pnl_values = [t.profit_loss or 0.0 for t in trades]
        rr_values = [t.risk_reward for t in trades if t.risk_reward is not None]
 
        stats['wins'] = len(wins)
        stats['losses'] = len(losses)
        stats['total_trades'] = len(trades)
        stats['win_rate'] = (len(wins) / len(trades) * 100) if trades else 0.0
        stats['total_pnl'] = sum(pnl_values)
        stats['avg_win'] = (
            sum(t.profit_loss for t in wins) / len(wins) if wins else 0.0
        )
        stats['avg_loss'] = (
            abs(sum(t.profit_loss for t in losses)) / len(losses) if losses else 0.0
        )
        stats['avg_rr'] = sum(rr_values) / len(rr_values) if rr_values else 0.0
        stats['best_trade'] = max(trades, key=lambda t: t.profit_loss or 0)
        stats['worst_trade'] = min(trades, key=lambda t: t.profit_loss or 0)
        return stats
 
    def _group_by_field(
        self, trades: List[Trade], field: str, min_count: int = 3
    ) -> Dict[str, Any]:
        groups: Dict[str, List[Trade]] = defaultdict(list)
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
        result = _copy_empty_setups()
        if not trades:
            return result
 
        strategy_stats = self._group_by_field(trades, 'strategy', min_count=3)
        instrument_stats = self._group_by_field(trades, 'symbol', min_count=3)
        emotion_stats = self._group_by_field(trades, 'emotion', min_count=3)
 
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
        by_day: Dict[int, List[Trade]] = defaultdict(list)
        day_names = [
            'Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday'
        ]
        for trade in trades:
            if trade.entry_date:
                # Support both aware and naive datetimes
                entry = trade.entry_date
                if hasattr(entry, 'weekday'):
                    by_day[entry.weekday()].append(trade)
 
        filtered = {
            day: self._trade_stats(items)
            for day, items in by_day.items()
            if len(items) >= 3
        }
        if not filtered:
            return {}
 
        best_record = max(filtered.items(), key=lambda x: x[1]['win_rate'])
        worst_record = min(filtered.items(), key=lambda x: x[1]['win_rate'])
        return {
            'best_day': {'name': day_names[best_record[0]], **best_record[1]},
            'worst_day': {'name': day_names[worst_record[0]], **worst_record[1]},
        }
 
    def _build_strengths_weaknesses(
        self, stats: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        strengths: List[str] = []
        weaknesses: List[str] = []
 
        total = stats.get('total_trades', 0)
        win_rate = stats.get('win_rate', 0.0)
        avg_rr = stats.get('avg_rr', 0.0)
        total_pnl = stats.get('total_pnl', 0.0)
 
        if win_rate >= 55 and total >= 3:
            strengths.append('Your win rate is strong for the current sample.')
        if avg_rr >= 2:
            strengths.append('Good risk-reward ratio on average.')
        if total_pnl > 0:
            strengths.append('You are trading profitably overall.')
        if win_rate < 45:
            weaknesses.append('Your win rate is lower than the ideal 50% threshold.')
        if avg_rr < 1.5:
            weaknesses.append('Average reward relative to risk is weak.')
        if total_pnl < 0:
            weaknesses.append('Your net result is negative. Review losing setups.')
 
        return {'strengths': strengths, 'weaknesses': weaknesses}
 
    def _detect_overtrading(self, trades: List[Trade]) -> bool:
        window = 7
        cutoff_aware = self.now - timedelta(days=window)
        cutoff_naive = cutoff_aware.replace(tzinfo=None)
        recent = []
        for t in trades:
            if t.entry_date is None:
                continue
            try:
                # Compare like-for-like (both aware or both naive)
                if t.entry_date.tzinfo is not None:
                    recent.append(t) if t.entry_date >= cutoff_aware else None
                else:
                    recent.append(t) if t.entry_date >= cutoff_naive else None
            except Exception:
                pass
        return len(recent) >= 10
 
    def _detect_revenge_trading(self, trades: List[Trade]) -> bool:
        losses: List[Trade] = []
        prev_loss = False
        for trade in sorted(
            trades,
            key=lambda t: (t.entry_date or datetime.min).replace(tzinfo=None)
            if (t.entry_date and t.entry_date.tzinfo is None)
            else (t.entry_date or datetime.min.replace(tzinfo=timezone.utc))
        ):
            if prev_loss:
                losses.append(trade)
            prev_loss = trade.profit_loss is not None and trade.profit_loss < 0
 
        if not losses:
            return False
        loss_rate = (
            len([t for t in losses if t.profit_loss and t.profit_loss < 0])
            / len(losses) * 100
        )
        return loss_rate > 50 and len(losses) >= 3
 
    def _get_risk_issues(self, trades: List[Trade]) -> List[str]:
        issues: List[str] = []
        high_risk_trades = [
            t for t in trades if t.risk_percentage and t.risk_percentage > 2
        ]
        low_rr_trades = [
            t for t in trades if t.risk_reward is not None and t.risk_reward < 1
        ]
        missing_stop_loss = [t for t in trades if not t.stop_loss]
 
        if high_risk_trades:
            issues.append(
                f'{len(high_risk_trades)} trade(s) risked more than 2% of account.'
            )
        if low_rr_trades:
            issues.append(f'{len(low_rr_trades)} trade(s) had R:R below 1:1.')
        if missing_stop_loss:
            issues.append(f'{len(missing_stop_loss)} trade(s) had no stop loss.')
        return issues
 
    def _get_mood_issues(self, trades: List[Trade]) -> List[str]:
        issues: List[str] = []
        try:
            detector = EmotionAnalyzer(self.user_id)
            performance = detector.get_emotion_performance(days=90)
            if not isinstance(performance, dict):
                return issues
            negative_emotions = getattr(EmotionAnalyzer, 'NEGATIVE_EMOTIONS', [])
            for emotion, data in performance.items():
                if not isinstance(data, dict):
                    continue
                win_rate = data.get('win_rate', 100)
                if emotion in negative_emotions and win_rate < 50:
                    issues.append(
                        f'{emotion} trades win only {win_rate:.0f}% of the time.'
                    )
        except Exception:
            pass
        return issues
 
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
 
    def get_weekly_review(self) -> Dict[str, Any]:
        self._load_trades(days=30)
        cutoff_aware = self.now - timedelta(days=7)
        cutoff_naive = cutoff_aware.replace(tzinfo=None)
 
        weekly_trades: List[Trade] = []
        for t in self.closed_trades:
            if t.exit_date is None:
                continue
            try:
                if t.exit_date.tzinfo is not None:
                    if t.exit_date >= cutoff_aware:
                        weekly_trades.append(t)
                else:
                    if t.exit_date >= cutoff_naive:
                        weekly_trades.append(t)
            except Exception:
                pass
 
        stats = self._trade_stats(weekly_trades)
        setups = self._best_setup(weekly_trades)
        day_insights = self._best_day(weekly_trades)
        alerts: List[str] = []
 
        try:
            if self._detect_overtrading(self.trades):
                alerts.append(
                    'Overtrading detected: too many trades in the last 7 days.'
                )
        except Exception:
            pass
 
        try:
            if self._detect_revenge_trading(weekly_trades):
                alerts.append('Revenge trading pattern detected after losses.')
        except Exception:
            pass
 
        try:
            alerts.extend(self._get_risk_issues(weekly_trades))
        except Exception:
            pass
 
        try:
            alerts.extend(self._get_mood_issues(weekly_trades))
        except Exception:
            pass
 
        strengths_weaknesses = self._build_strengths_weaknesses(stats)
        summary_text = self._build_summary_text(stats, setups, day_insights)
 
        return {
            'label': 'AI Buddy Weekly Review',
            'period': 'Last 7 days',
            'stats': stats,
            'setups': setups,
            'day_insights': day_insights,
            'alerts': alerts,
            'strengths': strengths_weaknesses['strengths'],
            'weaknesses': strengths_weaknesses['weaknesses'],
            'recommendations': self._get_recommendations(stats, setups),
            'summary': summary_text,
        }
 
    def get_monthly_review(self) -> Dict[str, Any]:
        self._load_trades(days=90)
        cutoff_aware = self.now - timedelta(days=30)
        cutoff_naive = cutoff_aware.replace(tzinfo=None)
 
        monthly_trades: List[Trade] = []
        for t in self.closed_trades:
            if t.exit_date is None:
                continue
            try:
                if t.exit_date.tzinfo is not None:
                    if t.exit_date >= cutoff_aware:
                        monthly_trades.append(t)
                else:
                    if t.exit_date >= cutoff_naive:
                        monthly_trades.append(t)
            except Exception:
                pass
 
        stats = self._trade_stats(monthly_trades)
        win_rate = stats.get('win_rate', 0.0)
        total_pnl = stats.get('total_pnl', 0.0)
        total_trades = stats.get('total_trades', 0)
 
        direction = (
            'improving'
            if total_trades and win_rate >= 50
            else 'needs review'
        )
        return {
            'label': 'AI Buddy Monthly Review',
            'period': 'Last 30 days',
            'stats': stats,
            'direction': direction,
            'summary': (
                f"Your last 30-day performance is {direction} with "
                f"{win_rate:.0f}% wins and ${total_pnl:.2f} P/L."
            ),
        }
 
    def get_behavioral_insights(self) -> Dict[str, Any]:
        self._load_trades(days=90)
 
        # PerformanceCalculator.calculate() may return an object with None fields
        discipline_score = 0.0
        consistency_score = 0.0
        try:
            score_obj = PerformanceCalculator(self.user_id).calculate()
            discipline_score = round(score_obj.discipline_score or 0, 1)
            consistency_score = round(score_obj.consistency_score or 0, 1)
        except Exception:
            pass
 
        negative_emotions_set = set(
            getattr(EmotionAnalyzer, 'NEGATIVE_EMOTIONS', [])
        )
        positive_emotions_set = set(
            getattr(EmotionAnalyzer, 'POSITIVE_EMOTIONS', [])
        )
 
        negative_emotions = [
            t for t in self.trades if t.emotion in negative_emotions_set
        ]
        confidence_values = [
            t.confidence_level
            for t in self.trades
            if t.confidence_level is not None
        ]
 
        trades_with_rr = [t for t in self.trades if t.risk_reward is not None]
        avg_rr = (
            round(
                sum(t.risk_reward for t in trades_with_rr) / len(trades_with_rr),
                2,
            )
            if trades_with_rr
            else 0.0
        )
 
        return {
            'discipline_score': discipline_score,
            'consistency_score': consistency_score,
            'emotional_bias': (
                f"{len(negative_emotions)} emotional trades in last 90 days"
            ),
            'confidence_trend': (
                round(sum(confidence_values) / len(confidence_values), 1)
                if confidence_values
                else None
            ),
            'risk_behavior': {
                'avg_rr': avg_rr,
                'high_risk_trades': len(
                    [t for t in self.trades if t.risk_percentage and t.risk_percentage > 2]
                ),
            },
        }
 
    def _build_summary_text(
        self,
        stats: Dict[str, Any],
        setups: Dict[str, Any],
        day_insights: Dict[str, Any],
    ) -> str:
        total = stats.get('total_trades', 0)
        if total == 0:
            return (
                'No closed trades recorded this week. '
                'Log trades to get AI Buddy insights.'
            )
 
        win_rate = stats.get('win_rate', 0.0)
        total_pnl = stats.get('total_pnl', 0.0)
        intro = (
            f"This week you took {total} closed trades with a "
            f"{win_rate:.0f}% win rate and ${total_pnl:.2f} P/L."
        )
 
        best_strategy = (setups or {}).get('best_strategy')
        if best_strategy and isinstance(best_strategy, dict):
            name = best_strategy.get('name', '')
            wr = best_strategy.get('win_rate', 0.0)
            intro += f" Your best strategy was {name} with a {wr:.0f}% win rate."
 
        best_day = (day_insights or {}).get('best_day')
        if best_day and isinstance(best_day, dict):
            name = best_day.get('name', '')
            wr = best_day.get('win_rate', 0.0)
            intro += f" Your strongest day was {name} with a {wr:.0f}% win rate."
 
        return intro
 
    def _get_recommendations(
        self, stats: Dict[str, Any], setups: Dict[str, Any]
    ) -> List[str]:
        recommendations: List[str] = []
        win_rate = stats.get('win_rate', 0.0)
        avg_rr = stats.get('avg_rr', 0.0)
        total_pnl = stats.get('total_pnl', 0.0)
 
        if win_rate < 50:
            recommendations.append(
                'Review your losing setups and avoid weak sessions.'
            )
        if avg_rr < 1.5:
            recommendations.append(
                'Improve risk management by targeting R:R above 1.5:1.'
            )
        if total_pnl < 0:
            recommendations.append(
                'Focus on quality setups and avoid emotional entries.'
            )
 
        best_strategy = (setups or {}).get('best_strategy')
        if best_strategy and isinstance(best_strategy, dict):
            name = best_strategy.get('name', '')
            if name:
                recommendations.append(
                    f'Trade more with {name} when conditions are aligned.'
                )
 
        worst_strategy = (setups or {}).get('worst_strategy')
        if worst_strategy and isinstance(worst_strategy, dict):
            name = worst_strategy.get('name', '')
            wr = worst_strategy.get('win_rate', 100.0)
            if name and wr < 40:
                recommendations.append(
                    f'Avoid {name} until you review the edge.'
                )
 
        return recommendations
 
    def get_voice_summary(self) -> str:
        try:
            review = self.get_weekly_review()
            stats = review.get('stats', _copy_empty_stats())
            setups = review.get('setups', _copy_empty_setups())
            total = stats.get('total_trades', 0)
            win_rate = stats.get('win_rate', 0.0)
            best_strategy = setups.get('best_strategy')
            strategy_name = (
                best_strategy.get('name', 'your strongest strategy')
                if isinstance(best_strategy, dict)
                else 'your strongest strategy'
            )
            return (
                f"Hello trader, this week you took {total} closed trades. "
                f"Your win rate was {win_rate:.0f} percent. "
                f"Your biggest strength was {strategy_name}. "
                f"Your biggest opportunity is to improve your risk reward "
                f"and reduce emotional trades."
            )
        except Exception:
            return (
                'AI Buddy has no data to summarise yet. '
                'Log some trades to get started.'
            )
 
    def answer_question(self, question: str) -> str:
        if not question:
            return 'Ask me anything about your recent trading performance.'
 
        text = question.strip().lower()
 
        try:
            weekly = self.get_weekly_review()
        except Exception:
            weekly = {
                'summary': 'No data available.',
                'alerts': [],
                'recommendations': [],
                'stats': _copy_empty_stats(),
                'setups': _copy_empty_setups(),
            }
 
        try:
            behavioral = self.get_behavioral_insights()
        except Exception:
            behavioral = {
                'discipline_score': 0.0,
                'consistency_score': 0.0,
            }
 
        if 'perform' in text and 'week' in text:
            return weekly.get('summary', 'No weekly data available yet.')
 
        if 'mistake' in text or 'mistakes' in text:
            issues = weekly.get('alerts', [])[:3]
            return (
                ' '.join(issues)
                if issues
                else (
                    'Your biggest mistakes are low R:R and emotional trade entries. '
                    'Review your recent losing trades.'
                )
            )
 
        if 'best setup' in text:
            best = (weekly.get('setups') or {}).get('best_strategy')
            if best and isinstance(best, dict):
                name = best.get('name', '')
                wr = best.get('win_rate', 0.0)
                return f"Your best setup is {name} with a {wr:.0f}% win rate."
            return 'You do not have a clear best setup yet.'
 
        if 'improve' in text:
            recs = weekly.get('recommendations') or []
            return (
                ' '.join(recs)
                if recs
                else (
                    'Focus on rule-based entries, stronger risk management, '
                    'and better emotional control.'
                )
            )
 
        if 'why' in text and 'losing' in text:
            total_pnl = (weekly.get('stats') or {}).get('total_pnl', 0.0)
            if total_pnl < 0:
                return (
                    'You are losing because your average R:R is low and you are '
                    'trading during weak sessions or emotional states. Improve '
                    'risk control and avoid revenge trades.'
                )
            return (
                'Your losses are likely due to occasional weak setups or poor '
                'plan adherence. Review your trade notes and stop-loss discipline.'
            )
 
        return weekly.get('summary', 'No data available yet. Log some trades to get started.')
 
 
def get_ai_insights(user_id: int) -> Dict[str, Any]:
    analyzer = AIAnalyzer(user_id)
    try:
        weekly_review = analyzer.get_weekly_review()
    except Exception:
        weekly_review = {}
    try:
        monthly_review = analyzer.get_monthly_review()
    except Exception:
        monthly_review = {}
    try:
        behavioral_insights = analyzer.get_behavioral_insights()
    except Exception:
        behavioral_insights = {}
    try:
        voice_summary = analyzer.get_voice_summary()
    except Exception:
        voice_summary = ''
    return {
        'weekly_review': weekly_review,
        'monthly_review': monthly_review,
        'behavioral_insights': behavioral_insights,
        'voice_summary': voice_summary,
    }
