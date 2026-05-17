"""
AI Buddy Insights Service
Builds advanced performance and behavioral insights from real trade data.
All methods are defensively coded to return safe defaults when no trade data exists.
"""
 
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import random
import re
from typing import List, Dict, Any
 
from sqlalchemy import or_, func
 
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.services.emotion_analyzer import EmotionAnalyzer
from app.services.performance_calculator import PerformanceCalculator
from app.services.trading_knowledge import match_topic, render_topic
from app.services.ai_coach_context import format_coach_context_block
 
 
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
 
        total = int(stats.get('total_trades', 0) or 0)
        if total < 1:
            return {'strengths': [], 'weaknesses': []}

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
 
        has_data = int(stats.get('total_trades') or 0) > 0
        return {
            'label': 'AI Buddy Weekly Review',
            'period': 'Last 7 days',
            'has_data': has_data,
            'stats': stats,
            'setups': setups,
            'day_insights': day_insights,
            'alerts': alerts if has_data else [],
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
 
        if total_trades < 1:
            return {
                'label': 'AI Buddy Monthly Review',
                'period': 'Last 30 days',
                'has_data': False,
                'stats': stats,
                'direction': 'onboarding',
                'summary': (
                    'No closed trades in the last 30 days yet. '
                    'Log a few closed trades and AI Buddy will track your trend here.'
                ),
            }

        direction = 'improving' if win_rate >= 50 and total_pnl >= 0 else 'needs review'
        if direction == 'improving':
            summary = (
                f"Your last 30-day performance is improving, with "
                f"{win_rate:.0f}% wins and ${total_pnl:.2f} P/L."
            )
        else:
            summary = (
                f"Your last 30-day performance needs review: "
                f"{win_rate:.0f}% wins and ${total_pnl:.2f} P/L."
            )
        return {
            'label': 'AI Buddy Monthly Review',
            'period': 'Last 30 days',
            'has_data': True,
            'stats': stats,
            'direction': direction,
            'summary': summary,
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
 
        closed_count = len(self.closed_trades)
        return {
            'has_data': closed_count > 0,
            'discipline_score': discipline_score if closed_count else None,
            'consistency_score': consistency_score if closed_count else None,
            'emotional_bias': (
                f"{len(negative_emotions)} emotional trades in last 90 days"
                if closed_count
                else 'Log trades to see emotional patterns'
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
        total = int(stats.get('total_trades', 0) or 0)
        if total < 1:
            return [
                'Log your next 3 closed trades with stop loss, strategy tag, and 1–2 lines of post-trade notes.',
                'Set one weekly focus rule (max trades per day or daily stop in R).',
                'Run Trade Doctor again once you have at least 5 closed trades.',
            ]

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
 
    def get_voice_review(self, user_name: str = '') -> Dict[str, Any]:
        """Return a richer, less-robotic voice review payload.

        This stays deterministic-ish (varies by week + stats) so it feels fresh
        without becoming random noise.
        """
        weekly = {}
        try:
            weekly = self.get_weekly_review() or {}
        except Exception:
            weekly = {}

        stats = (weekly.get('stats') or _copy_empty_stats())
        setups = (weekly.get('setups') or _copy_empty_setups())
        day_insights = (weekly.get('day_insights') or {})
        alerts = (weekly.get('alerts') or [])[:3]
        strengths = (weekly.get('strengths') or [])[:3]
        weaknesses = (weekly.get('weaknesses') or [])[:3]
        recs = (weekly.get('recommendations') or [])[:3]

        total = int(stats.get('total_trades') or 0)
        win_rate = float(stats.get('win_rate') or 0.0)
        total_pnl = float(stats.get('total_pnl') or 0.0)
        avg_rr = float(stats.get('avg_rr') or 0.0)

        best_strategy = setups.get('best_strategy') if isinstance(setups, dict) else None
        best_name = ''
        if isinstance(best_strategy, dict):
            best_name = str(best_strategy.get('name') or '')

        # Stable seed: ISO week + closed trade count (avoids repeating tone forever)
        try:
            seed = int(self.now.strftime('%G%V')) * 1000 + total
        except Exception:
            seed = total or 1
        rng = random.Random(seed)

        def pick(options: List[str]) -> str:
            return rng.choice(options) if options else ''

        greet_name = (user_name or '').strip()
        greet = pick([
            f"Hey {greet_name}—quick coach brief.",
            f"Alright {greet_name}, here’s your weekly review.",
            f"{greet_name}, let’s review your week like a pro.",
            "Quick coach brief—here’s the week.",
            "Let’s break down your week."
        ])
        greet = greet.replace("—", ",") if not greet_name else greet

        if total <= 0:
            segments = [
                greet,
                "You don’t have any closed trades logged this week.",
                "If you want me to coach you properly, log at least your entry, exit, and stop loss—or your risk amount.",
                "Question: what’s the one setup you’re focusing on next week?"
            ]
            return {
                'text': ' '.join(segments),
                'segments': segments,
                'questions': ["What’s the one setup you’re focusing on next week?"],
                'meta': {'trades': total, 'win_rate': win_rate, 'total_pnl': total_pnl, 'avg_rr': avg_rr}
            }

        best_day_name = ''
        best_day_wr = None
        try:
            bd = day_insights.get('best_day')
            if isinstance(bd, dict):
                best_day_name = str(bd.get('name') or '')
                best_day_wr = float(bd.get('win_rate') or 0.0)
        except Exception:
            best_day_name = ''

        best_trade = stats.get('best_trade')
        worst_trade = stats.get('worst_trade')
        best_trade_line = ''
        worst_trade_line = ''
        try:
            if best_trade and getattr(best_trade, 'symbol', None) and getattr(best_trade, 'profit_loss', None) is not None:
                best_trade_line = f"Best trade: {best_trade.symbol} {best_trade.profit_loss:.0f}."
        except Exception:
            best_trade_line = ''
        try:
            if worst_trade and getattr(worst_trade, 'symbol', None) and getattr(worst_trade, 'profit_loss', None) is not None:
                worst_trade_line = f"Worst trade: {worst_trade.symbol} {worst_trade.profit_loss:.0f}."
        except Exception:
            worst_trade_line = ''

        pnl_phrase = pick([
            f"Net P and L: {total_pnl:.0f}.",
            f"You’re at {total_pnl:.0f} net for the week.",
            f"Your week finished at {total_pnl:.0f} total."
        ])

        wr_phrase = pick([
            f"Win rate: {win_rate:.0f} percent across {total} trades.",
            f"You took {total} trades with a {win_rate:.0f} percent win rate.",
            f"{total} trades logged, {win_rate:.0f} percent winners."
        ])

        rr_phrase = pick([
            f"Average R to R: {avg_rr:.2f}.",
            f"Your average risk reward was {avg_rr:.2f}.",
            f"Risk reward averaged {avg_rr:.2f}."
        ])

        best_phrase = (
            pick([
                f"Your strongest edge showed up in {best_name}.",
                f"Best setup this week was {best_name}.",
                f"Your best-performing strategy: {best_name}."
            ]) if best_name else pick([
                "No single strategy dominated this week.",
                "Your results were spread—no clear best setup yet.",
                "You don’t have a clear best strategy in this sample."
            ])
        )

        best_day_phrase = (
            pick([
                f"Your strongest day was {best_day_name} at {best_day_wr:.0f} percent.",
                f"Best day: {best_day_name}, {best_day_wr:.0f} percent win rate.",
            ]) if best_day_name and best_day_wr is not None and total >= 3 else ""
        )

        strength_line = strengths[0] if strengths else pick([
            "Strength: you showed discipline in at least part of the sample.",
            "Strength: you’re tracking enough data to improve.",
        ])
        weakness_line = weaknesses[0] if weaknesses else pick([
            "Leak: risk reward is your biggest lever this week.",
            "Leak: consistency and selectivity look like the next upgrade."
        ])

        one_rule = pick(recs) if recs else pick([
            "One rule: only take trades that meet your checklist—no exceptions.",
            "One rule: predefine risk before entry, every single time.",
            "One rule: if you feel rushed, you don’t trade."
        ])

        follow_up = pick([
            "Quick question: what was the one emotion you felt most before entering trades this week?",
            "Quick question: what time of day did you take most of your losing trades?",
            "Quick question: did you move your stop loss on any trade this week?"
        ])

        segments = [greet, wr_phrase, pnl_phrase, rr_phrase, best_phrase]
        if best_day_phrase:
            segments.append(best_day_phrase)
        if best_trade_line:
            segments.append(best_trade_line)
        if worst_trade_line:
            segments.append(worst_trade_line)
        if alerts:
            segments.append("Top alerts: " + "; ".join(alerts) + ".")
        segments.extend([strength_line, weakness_line, f"Your one rule for next week: {one_rule}", follow_up])
        text = ' '.join(s for s in segments if s)
        return {
            'text': text,
            'segments': segments,
            'questions': [follow_up],
            'meta': {'trades': total, 'win_rate': win_rate, 'total_pnl': total_pnl, 'avg_rr': avg_rr, 'best_strategy': best_name}
        }

    def _answer_evidence_prefix(
        self, stats: Dict[str, Any], coach_context: str = ''
    ) -> str:
        total = int(stats.get('total_trades') or 0)
        block = (coach_context or '').strip()
        if total < 1:
            head = (
                "**Your data (last 7 days):** No closed trades yet.\n"
                "Log 3+ closed trades with stop loss, strategy tags, and short post-trade notes."
            )
        else:
            head = (
                f"**Your data (last 7 days):** {total} trades, "
                f"{float(stats.get('win_rate') or 0):.0f}% win rate, "
                f"net {float(stats.get('total_pnl') or 0):.2f}, "
                f"avg R:R {float(stats.get('avg_rr') or 0):.2f}."
            )
        if block:
            return head + "\n\n" + block + "\n\n"
        return head + "\n\n"

    def _wrap_coach_answer(
        self, body: str, stats: Dict[str, Any], coach_context: str = ''
    ) -> str:
        return self._answer_evidence_prefix(stats, coach_context) + (body or "").strip()

    def _empty_state_coach_reply(self, stats: Dict[str, Any], coach_context: str = '') -> Dict[str, Any]:
        body = (
            "I don’t have enough of *your* trade data to diagnose a leak yet.\n\n"
            "**Do this next (takes ~10 minutes):**\n"
            "- Log **3 closed trades** with stop loss (or risk $), strategy tag, and emotion.\n"
            "- Add **1–2 lines** of post-trade notes on each (what was sloppy vs correct).\n"
            "- Set **one weekly focus rule** (example: max 2 trades/day; stop after −2R).\n\n"
            "Then ask: *“What’s my biggest leak?”* or run **Trade Doctor**."
        )
        return {
            'answer': self._wrap_coach_answer(body, stats, coach_context),
            'follow_ups': [
                "What should I log on every trade?",
                "Give me a pre-trade checklist.",
                "Suggest a weekly focus rule for me.",
            ],
        }

    def get_morning_briefing(self, user_name: str = '') -> Dict[str, Any]:
        """Three-line coach briefing for the Today tab."""
        weekly = self.get_weekly_review() or {}
        stats = weekly.get('stats') or _copy_empty_stats()
        alerts = weekly.get('alerts') or []
        recs = weekly.get('recommendations') or []
        total = int(stats.get('total_trades') or 0)
        name = (user_name or '').strip() or 'Trader'

        if total < 1:
            lines = [
                f"Good session, {name}. Your journal is ready — add your first closed trade when you finish one.",
                "Focus today: one setup, one market, one session window.",
                "Set a weekly focus rule (even one sentence) so I can coach you against it.",
            ]
        else:
            pnl = float(stats.get('total_pnl') or 0)
            wr = float(stats.get('win_rate') or 0)
            lines = [
                f"Good session, {name}. Last 7 days: {total} trades, {wr:.0f}% win rate, net {pnl:+.2f}.",
                (alerts[0] if alerts else (recs[0] if recs else "Keep tagging strategy and emotion on every trade.")),
                recs[0] if recs and not alerts else (
                    recs[0] if recs else "Review yesterday’s loss — was it process or impulse?"
                ),
            ]
        return {'lines': lines[:3], 'has_data': total > 0}

    def get_last_trade_insight(self) -> str:
        """One sentence after the most recent closed trade (dashboard pulse)."""
        try:
            t = (
                Trade.query.filter(
                    Trade.user_id == self.user_id,
                    Trade.status == "CLOSED",
                    Trade.profit_loss.isnot(None),
                )
                .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
                .first()
            )
        except Exception:
            t = None
        if not t:
            return ""
        pnl = float(t.profit_loss or 0)
        sym = t.symbol or "trade"
        emo = (t.emotion or "").strip()
        note = (t.post_trade_notes or t.lessons_learned or "").strip()
        if pnl > 0:
            tone = "Winner logged"
        elif pnl < 0:
            tone = "Loss logged"
        else:
            tone = "Trade closed"
        line = f"{tone} on {sym} ({pnl:+.2f})."
        if emo:
            line += f" Emotion: {emo}."
        if note:
            snippet = note[:120] + ("..." if len(note) > 120 else "")
            line += f" Note: {snippet}"
        elif pnl < 0:
            line += " Add a one-line lesson so AI Buddy can spot patterns."
        return line

    @staticmethod
    def _direct_ack(question: str, *, max_len: int = 140) -> str:
        """One-line reminder that the coach is answering what the user asked."""
        q = (question or '').strip()
        if not q:
            return ''
        display = (q[:max_len] + '…') if len(q) > max_len else q
        return f"**Answering:** *{display}*\n\n"

    @staticmethod
    def _is_personal_performance_question(text: str) -> bool:
        """True when the user is asking about their own journal stats (not general education)."""
        t = (text or '').lower()
        markers = (
            'my win rate', 'my performance', 'my trades', 'my best', 'my worst', 'my biggest',
            'my pnl', 'my profit', 'my loss', 'my stats', 'my journal', 'my account', 'my edge',
            'my trading', 'my results', 'my data', 'my week', 'my month',
            'how did i', 'how have i', 'how am i', 'how many trades', 'how much did i',
            'this week', 'last week', 'biggest leak', 'performance leak',
            'best strategy', 'best setup', 'worst strategy', 'trade doctor',
            'how am i doing', 'how have i been', 'am i profitable', 'am i winning',
            'based on my', 'from my trades', 'in my journal', 'for me based',
            'suggest a rule for me', 'suggest a weekly', 'one rule for me',
        )
        if any(m in t for m in markers):
            return True
        if 'perform' in t and any(x in t for x in ('my ', 'i ', 'this week', 'weekly')):
            return True
        if any(w in t for w in ('mistake', 'leak', 'losing money', 'losing on')) and (
            'my ' in t or ' i ' in t or t.startswith('i ')
        ):
            return True
        if re.search(r'\b(i|my)\b.{0,40}\b(win rate|pnl|profit|loss|trades?|performance|doing)\b', t):
            return True
        if re.search(r'\b(what|how many|how much)\b.{0,30}\b(my|i)\b', t):
            return True
        return False

    def suggest_weekly_focus_rule(self) -> str:
        """Auto-suggest one weekly rule from alerts / Trade Doctor."""
        weekly = self.get_weekly_review() or {}
        alerts = weekly.get('alerts') or []
        recs = weekly.get('recommendations') or []
        if alerts:
            a = alerts[0]
            if 'overtrading' in a.lower():
                return "Max 2 trades per day; stop after 2 losses."
            if 'revenge' in a.lower():
                return "After any loss: 15-minute break before the next entry."
            if 'risk' in a.lower() or 'r:r' in a.lower():
                return "No trade without SL and planned R:R ≥ 1:1.5."
            return f"Address this week: {a[:120]}"
        if recs:
            return recs[0][:200]
        td = self.trade_doctor(last_n=10)
        leak = (td.get('leak') or '').strip()
        if leak and leak not in ('No recent closed trades', 'Need more signal'):
            return f"Trade Doctor focus: {leak[:160]}"
        return "Max 2 trades per day; stop trading after −2R daily loss."

    def answer_question(
        self,
        question: str,
        *,
        history: List[Dict[str, str]] | None = None,
        user_name: str = '',
        coach_context: str = '',
    ) -> Dict[str, Any]:
        """Answer with both trade-grounded context and general trading knowledge.

        Returns a structured payload so the UI can render follow-ups and avoid repetition.
        """
        q = (question or '').strip()
        if not q:
            return {
                'answer': 'Ask me anything about your recent performance or about trading in general.',
                'follow_ups': [
                    "What’s my biggest performance leak this week?",
                    "What should my one rule be next week?",
                    "Explain risk:reward like I’m new to trading."
                ]
            }

        text = q.lower()
        hist = history or []
        last_assistant = ''
        for msg in reversed(hist):
            if msg.get('role') == 'assistant' and msg.get('content'):
                last_assistant = str(msg.get('content'))
                break

        try:
            weekly = self.get_weekly_review() or {}
        except Exception:
            weekly = {}
        stats = (weekly.get('stats') or _copy_empty_stats())
        setups = (weekly.get('setups') or _copy_empty_setups())
        day_insights = (weekly.get('day_insights') or {})
        alerts = (weekly.get('alerts') or [])
        recs = (weekly.get('recommendations') or [])

        total = int(stats.get('total_trades') or 0)
        win_rate = float(stats.get('win_rate') or 0.0)
        total_pnl = float(stats.get('total_pnl') or 0.0)
        avg_rr = float(stats.get('avg_rr') or 0.0)

        # Simple intent detection (expanded beyond a few keywords)
        def has(*words: str) -> bool:
            return any(w in text for w in words)

        personal = self._is_personal_performance_question(text)
        if total < 1 and personal:
            return self._empty_state_coach_reply(stats, coach_context)

        def _coach_basics() -> str:
            """
            Professional baseline guidance for broad questions.
            Keeps it actionable and consistent with a journaling app (not news-driven).
            """
            lines = [
                "Here’s the fastest way to improve (the *professional* version):",
                "",
                "**1) Protect downside first (risk policy)**",
                "- Risk a fixed amount per trade (ex: 0.25–1.0% of account).",
                "- Hard rule: stop trading after a daily loss limit (ex: −2R) or 2 consecutive losses.",
                "",
                "**2) Define one repeatable setup (edge)**",
                "- One market + one session + one trigger. Write it as a checklist.",
                "- If you can’t describe the trigger in one sentence, it’s not repeatable yet.",
                "",
                "**3) Execute like a machine (process)**",
                "- Pre-trade: entry reason + SL/TP + invalidation (what proves you wrong).",
                "- Post-trade: 2–3 lines: what was correct, what was sloppy, what’s the fix.",
                "",
                "**4) Review weekly (feedback loop)**",
                "- Identify your #1 leak (overtrading, moving SL, low R:R, wrong session).",
                "- Convert it into ONE rule for next week.",
            ]
            if total > 0:
                lines += [
                    "",
                    f"Your recent sample: {total} closed trades, {win_rate:.0f}% win rate, net {total_pnl:.0f}, avg R:R {avg_rr:.2f}.",
                ]
                if avg_rr and avg_rr < 1.0:
                    lines.append("Coach note: your average R:R is under 1.0 — that’s a common profitability killer even with a decent win rate.")
                if win_rate and win_rate < 45:
                    lines.append("Coach note: win rate is low — focus on trade selection and session discipline before increasing size.")
            return self._wrap_coach_answer("\n".join(lines), stats, coach_context)

        # General trading knowledge topics (still tailored with your stats when possible)
        if has('risk', 'rr', 'r:r', 'risk reward', 'stop loss', 'sl', 'tp', 'take profit'):
            parts = [
                self._direct_ack(q),
                f"{user_name + ', ' if user_name else ''}here’s the clean way to think about risk and R-multiples:",
                "- Risk is what you lose if SL is hit (either in pips or $).",
                "- Reward is what you gain if TP is hit.",
                "- R:R is reward ÷ risk. Example: risking 1R to make 2R is 1:2.",
            ]
            if total > 0:
                parts.append(f"From your last week: average R:R ≈ {avg_rr:.2f}, win rate ≈ {win_rate:.0f}%, trades = {total}.")
                parts.append("If you raise R:R, you can stay profitable even with a lower win rate—but only if entries stay selective.")
            parts.append("If you want, tell me one recent trade (entry, SL, TP) and I’ll compute the exact R:R and what win rate you’d need.")
            answer = self._wrap_coach_answer("\n".join(parts), stats, coach_context)
            return {'answer': answer, 'follow_ups': ["What’s my current weak point: win rate or R:R?", "Give me a stop-loss rule I can follow.", "How do I size positions safely?"]}

        if personal and has(
            'pnl', 'profit', 'loss', 'net', 'how many', 'how much',
            'total trades', 'trades did', 'trades have', 'closed trades',
        ) and not has('explain', 'what is', 'define', 'how do i stop', 'how to stop'):
            summary = weekly.get('summary') or (
                f"Last 7 days: **{total}** closed trades, **{win_rate:.0f}%** win rate, "
                f"net **{total_pnl:+.2f}**, average R:R **{avg_rr:.2f}**."
            )
            body = self._direct_ack(q) + summary
            if alerts:
                body += "\n\n**Top issue to watch:** " + str(alerts[0])
            if recs:
                body += "\n\n**Next step:** " + str(recs[0])
            return {
                'answer': self._wrap_coach_answer(body, stats, coach_context),
                'follow_ups': [
                    "What’s my biggest performance leak this week?",
                    "What should my one rule be next week?",
                    "What’s my best strategy and why?",
                ],
            }

        if personal and has('win rate', 'wins', 'losses', 'performance', 'this week', 'weekly'):
            summary = weekly.get('summary') or ''
            if not summary:
                summary = f"Weekly snapshot: {total} closed trades, {win_rate:.0f}% win rate, net {total_pnl:.0f}, average R:R {avg_rr:.2f}."
            # Premium: structured coach brief with actions + evidence.
            answer = (
                self._direct_ack(q)
                + "**Weekly Coach Brief**\n"
                + summary
                + "\n\n**Top alerts (what’s costing you)**\n"
                + ("- " + "\n- ".join(alerts[:3]) if alerts else "- No strong alerts yet (log more trades + notes).")
                + "\n\n**Next actions (do these next)**\n"
                + ("- " + "\n- ".join(recs[:3]) if recs else "- Pick one leak and write one rule for next week.")
            )
            # Evidence lines
            try:
                best_trade = stats.get('best_trade')
                worst_trade = stats.get('worst_trade')
                if best_trade and getattr(best_trade, 'symbol', None) and getattr(best_trade, 'profit_loss', None) is not None:
                    answer += f"\n\n**Evidence**\n- Best trade: {best_trade.symbol} ({best_trade.profit_loss:.0f})"
                if worst_trade and getattr(worst_trade, 'symbol', None) and getattr(worst_trade, 'profit_loss', None) is not None:
                    answer += f"\n- Worst trade: {worst_trade.symbol} ({worst_trade.profit_loss:.0f})"
            except Exception:
                pass
            answer += "\n\n**One premium question for you:** What is your daily stop rule (in R)? If you don’t have one, I’ll give you one."
            return {
                'answer': self._wrap_coach_answer(answer, stats, coach_context),
                'follow_ups': ["What’s my biggest leak this week?", "Give me one rule for next week.", "Build me a pre-trade checklist."],
            }

        if has('best day', 'worst day', 'weekday', 'day of week'):
            bd = day_insights.get('best_day') if isinstance(day_insights, dict) else None
            wd = day_insights.get('worst_day') if isinstance(day_insights, dict) else None
            if isinstance(bd, dict) or isinstance(wd, dict):
                lines = []
                if isinstance(bd, dict):
                    lines.append(f"Best day: **{bd.get('name','—')}** — {float(bd.get('win_rate') or 0.0):.0f}% win rate ({int(bd.get('total_trades') or 0)} trades).")
                if isinstance(wd, dict):
                    lines.append(f"Worst day: **{wd.get('name','—')}** — {float(wd.get('win_rate') or 0.0):.0f}% win rate ({int(wd.get('total_trades') or 0)} trades).")
                lines.append("Coach move: trade your A+ setup more on your best day/session, and reduce size or skip on the worst day until reviewed.")
                return {
                    'answer': self._wrap_coach_answer("\n".join(lines), stats, coach_context),
                    'follow_ups': ["What’s my best session?", "What strategy wins most on my best day?", "How do I avoid forcing trades?"],
                }
            body = "I don’t have enough weekly trades to confidently rank days yet. Keep logging for another week and ask again."
            return {
                'answer': self._wrap_coach_answer(body, stats, coach_context),
                'follow_ups': ["What’s my weekly snapshot?", "What’s my biggest leak?"],
            }

        if personal and has('best setup', 'best strategy', 'my best', 'my edge'):
            best = (setups or {}).get('best_strategy')
            if best and isinstance(best, dict):
                name = str(best.get('name') or '')
                wr = float(best.get('win_rate') or 0.0)
                count = int(best.get('total_trades') or 0)
                answer = f"Best strategy in your recent sample: **{name}** — {wr:.0f}% win rate over {count} trades."
                answer += "\n\nCoach note: double down only if you can describe the entry trigger in one sentence and repeat it."
                return {
                    'answer': self._wrap_coach_answer(answer, stats, coach_context),
                    'follow_ups': [f"What are the conditions when {name} works best?", "What’s my worst strategy and why?", "Give me a checklist for this setup."],
                }
            body = "You don’t have a clear best setup yet (needs more tagged trades). Start tagging strategy consistently for the next 10 trades."
            return {
                'answer': self._wrap_coach_answer(body, stats, coach_context),
                'follow_ups': ["How should I tag strategies?", "What’s the fastest way to improve with low sample size?"],
            }

        if has('revenge', 'fomo', 'tilt', 'psychology', 'discipline', 'emotion'):
            kb_psy = match_topic(text)
            if kb_psy:
                kb_answer, kb_fups = render_topic(kb_psy)
                body = self._direct_ack(q) + kb_answer
                if personal and total > 0 and alerts:
                    body += (
                        "\n\n**From your journal this week:** "
                        + str(alerts[0])
                        + " — pick one rule and test it for 5 trades."
                    )
                return {
                    'answer': self._wrap_coach_answer(body, stats, coach_context),
                    'follow_ups': kb_fups[:3],
                }

        if personal and has(
            'mistake', 'mistakes', 'leak', 'why am i losing', 'overtrade', 'revenge', 'fomo', 'biggest',
        ):
            issues = (alerts or [])[:4]
            if issues:
                answer = (
                    self._direct_ack(q)
                    + "Here are the top issues I can actually see in your recent sample:\n- "
                    + "\n- ".join(issues)
                )
            else:
                answer = (
                    self._direct_ack(q)
                    + "I don’t have strong alert signals yet, so here are the most common profit leaks to audit:\n"
                    "- Low R:R (taking 0.5R winners but 1R losers)\n"
                    "- Trading outside your best session\n"
                    "- Moving SL / closing winners early\n"
                    "- Revenge/FOMO entries\n"
                    "\nIf you tell me your last 3 losses, I’ll classify the leak."
                )
            return {
                'answer': self._wrap_coach_answer(answer, stats, coach_context),
                'follow_ups': ["What’s my one rule next week?", "How do I stop revenge trading?", "Build me a pre-trade checklist."],
            }

        if has(
            'improve', 'get better', 'better trader',
            'how do i improve', 'how can i improve', 'help me',
        ) and not personal:
            return {
                'answer': _coach_basics(),
                'follow_ups': [
                    "What’s my biggest leak this week?",
                    "Give me one rule for next week.",
                    "Build me a pre-trade checklist for my best setup.",
                ],
            }

        if has('weekly focus', 'one rule', 'suggest a rule', 'focus rule'):
            suggested = self.suggest_weekly_focus_rule()
            body = (
                f"**Suggested weekly focus rule:**\n{suggested}\n\n"
                "Save it on the Coach setup tab (or tap **Use this rule** on Today)."
            )
            return {
                'answer': self._wrap_coach_answer(body, stats, coach_context),
                'follow_ups': ["What’s my biggest leak this week?", "Run Trade Doctor.", "Build me a pre-trade checklist."],
                'suggested_weekly_focus': suggested,
            }

        kb = match_topic(text)
        if kb and not personal:
            kb_answer, kb_fups = render_topic(kb)
            return {
                'answer': self._wrap_coach_answer(kb_answer, stats, coach_context),
                'follow_ups': kb_fups[:3],
            }

        # Direct answer: acknowledge the question instead of dumping an unrelated weekly summary
        body_parts = [self._direct_ack(q)]
        if kb:
            kb_answer, kb_fups = render_topic(kb)
            body_parts.append(kb_answer)
            follow_ups = kb_fups[:3]
        elif re.search(r'\bhow do i\b|\bwhat is\b|\bexplain\b|\bhow does\b|\bdefine\b', text):
            body_parts.append(
                "Here’s a practical framework:\n"
                "- Fix risk per trade and a daily stop (example: −2R or 2 losses).\n"
                "- Trade one repeatable setup with a written checklist.\n"
                "- Journal every trade with SL, emotion, and a one-line lesson."
            )
            follow_ups = [
                'Explain risk:reward and how to improve it.',
                'How do I journal properly?',
                "What’s my biggest leak this week?",
            ]
        elif personal and total > 0:
            base = weekly.get('summary') or (
                f"Recent snapshot: {total} closed trades, {win_rate:.0f}% win rate, "
                f"net {total_pnl:.0f}, avg R:R {avg_rr:.2f}."
            )
            body_parts.append(
                "Here’s what your journal shows that relates to your question:\n" + base
            )
            if alerts:
                body_parts.append("\n**Pattern I see:** " + str(alerts[0]))
            body_parts.append(
                "\nFor a sharper answer, try: *biggest leak*, *best strategy*, or *one rule for next week*."
            )
            follow_ups = [
                "What’s my biggest leak this week?",
                'What should my one rule be next week?',
                'What’s my best strategy and why?',
            ]
        else:
            body_parts.append(
                "I’m your trading coach — ask about risk, psychology, journaling, or your weekly stats. "
                "Try: “Explain risk:reward”, “How do I stop revenge trading?”, or “How did I perform this week?”"
            )
            follow_ups = [
                'Explain risk:reward and how to improve it.',
                'How do I stop revenge trading?',
                "What’s my biggest leak this week?",
            ]

        return {
            'answer': self._wrap_coach_answer('\n'.join(body_parts), stats, coach_context),
            'follow_ups': follow_ups[:3],
        }

    def trade_doctor(self, *, last_n: int = 10) -> Dict[str, Any]:
        """
        Premium: Inspect the last N closed trades and return the single biggest leak + a strict plan.
        This is deterministic and avoids generic advice.
        """
        try:
            trades = (
                Trade.query.filter(
                    Trade.user_id == self.user_id,
                    Trade.status == "CLOSED",
                    Trade.profit_loss.isnot(None),
                    Trade.exit_date.isnot(None),
                )
                .order_by(Trade.exit_date.desc())
                .limit(int(last_n))
                .all()
            )
        except Exception:
            trades = []

        if not trades:
            text = (
                "**Trade Doctor**\n\n"
                "Not enough closed trades yet. Log and close **at least 3 trades** with:\n"
                "- Strategy tag + emotion\n"
                "- Stop loss (or risk $)\n"
                "- One-line post-trade note\n\n"
                "Then run Trade Doctor again for a leak diagnosis."
            )
            return {
                "leak": "No recent closed trades",
                "evidence": ["Log and close at least 3 trades to unlock Trade Doctor."],
                "plan": [
                    "Log your next 10 trades with: strategy tag, emotion, SL, and a 1‑line plan.",
                    "Ask Trade Doctor again.",
                ],
                "checklist": [
                    "Strategy tag selected",
                    "SL placed (or risk $ entered)",
                    "Entry reason written in 1 sentence",
                    "Stop rule defined for the day (ex: −2R / 2 losses)",
                ],
                "text": text,
            }

        # Metrics
        pnl = [float(t.profit_loss or 0.0) for t in trades]
        wins = sum(1 for x in pnl if x > 0)
        losses = sum(1 for x in pnl if x < 0)
        zeros = sum(1 for x in pnl if x == 0)
        rr = [float(t.risk_reward) for t in trades if t.risk_reward is not None]
        avg_rr = sum(rr) / len(rr) if rr else None

        missing_risk = sum(1 for t in trades if not getattr(t, "stop_loss", None) and not getattr(t, "risk_amount", None))
        missing_tags = sum(1 for t in trades if not getattr(t, "strategy", None))
        low_quality = sum(1 for t in trades if (getattr(t, "execution_quality", None) or 0) and (getattr(t, "execution_quality", 0) <= 2))

        # Candidate leaks with scores (higher = more likely biggest)
        candidates: list[tuple[int, str, list[str], list[str], list[str]]] = []

        # Leak 1: undefined risk / no SL
        if missing_risk >= 3:
            evidence = [f"{missing_risk}/{len(trades)} of your last {len(trades)} trades had no SL or risk amount logged."]
            plan = [
                "Rule: No SL / no risk = no trade. Period.",
                "Set SL first, then size position (risk fixed per trade).",
                "If SL is technical and wide, reduce size; don’t widen risk.",
            ]
            checklist = [
                "SL placed at invalidation level",
                "Risk per trade fixed (ex: 0.5% or $X)",
                "Position sized from SL distance",
                "If SL moved, it’s only to reduce risk (never widen)",
            ]
            candidates.append((90 + missing_risk, "Undefined risk (missing SL/risk)", evidence, plan, checklist))

        # Leak 2: low R:R
        if avg_rr is not None and avg_rr < 1.2 and losses >= 3:
            evidence = [f"Average R:R over last {len(trades)} closed trades is ~{avg_rr:.2f}."]
            plan = [
                "Rule: Minimum planned R:R = 1:1.5 (prefer 1:2) before entering.",
                "Stop taking partials too early; scale only after consistency.",
                "Move SL to breakeven only after structure confirms, not immediately.",
            ]
            checklist = [
                "Planned R:R ≥ 1:1.5",
                "TP mapped to a real level (not random)",
                "No early close unless rule-based (time/news)",
                "Exit plan written before entry",
            ]
            candidates.append((80 + int((1.2 - avg_rr) * 50), "Low R:R (reward too small vs risk)", evidence, plan, checklist))

        # Leak 3: overtrading / churn (many trades, low edge)
        if len(trades) >= 8 and wins <= 3:
            evidence = [f"Last {len(trades)} trades: {wins}W / {losses}L / {zeros}BE. This looks like churn (too many B/C setups)."]
            plan = [
                "Rule: A+ setups only for the next 10 trades.",
                "Max 2 trades per day. Stop after 2 losses.",
                "Trade only your best session + one market.",
            ]
            checklist = [
                "Is this an A+ setup? (yes/no)",
                "Session matches your best window",
                "No trade after 2 losses",
                "2-trade max per day",
            ]
            candidates.append((75 + (len(trades) - wins), "Overtrading (too many low-quality attempts)", evidence, plan, checklist))

        # Leak 4: poor journaling signals (missing strategy tags / notes)
        if missing_tags >= 4:
            evidence = [f"{missing_tags}/{len(trades)} trades are missing a strategy tag."]
            plan = [
                "Rule: Every trade must be tagged with a strategy (even if it’s 'Other').",
                "Write a 1‑line pre-trade plan and 1‑line post-trade review.",
                "After 10 tagged trades, we’ll identify your true edge.",
            ]
            checklist = [
                "Strategy selected",
                "Pre-trade plan (1 sentence)",
                "Post-trade review (1 sentence)",
            ]
            candidates.append((60 + missing_tags, "Missing structure (no strategy tags / journaling)", evidence, plan, checklist))

        # Leak 5: execution issues
        if low_quality >= 3:
            evidence = [f"{low_quality}/{len(trades)} trades had low execution quality (≤2)."]
            plan = [
                "Rule: No market orders unless the setup is already triggered.",
                "Use alerts/levels; enter at level or skip.",
                "If you miss the entry, do NOT chase — wait for next setup.",
            ]
            checklist = [
                "Entry at level (no chase)",
                "Alert set before session",
                "If missed, skip without revenge",
            ]
            candidates.append((65 + low_quality, "Execution errors (chasing / poor entries)", evidence, plan, checklist))

        if not candidates:
            # Default: use “one rule” framing
            total_pnl = sum(pnl)
            leak = "Need more signal"
            evidence = [f"Last {len(trades)} trades: {wins}W / {losses}L, net {total_pnl:.2f}. Not enough tagged data to isolate one leak."]
            plan = [
                "Tag strategy + emotion for the next 10 trades.",
                "Log SL (or risk $) on every trade.",
                "Ask Trade Doctor again.",
            ]
            checklist = [
                "Strategy tag",
                "Emotion selected",
                "SL / risk recorded",
                "1-line plan written",
            ]
        else:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _score, leak, evidence, plan, checklist = candidates[0]

        # Strict plan wrapper
        strict = [
            f"**Trade Doctor diagnosis:** {leak}",
            "",
            "**Evidence (from last 10 closed trades)**",
            *[f"- {e}" for e in evidence],
            "",
            "**Strict plan (follow exactly for next 10 trades)**",
            *[f"- {p}" for p in plan],
        ]

        return {
            "leak": leak,
            "evidence": evidence,
            "plan": plan,
            "checklist": checklist,
            "text": "\n".join(strict),
        }
 
 
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
        voice_review = analyzer.get_voice_review()
        voice_summary = (voice_review.get('text') if isinstance(voice_review, dict) else '') or ''
    except Exception:
        voice_summary = ''
    return {
        'weekly_review': weekly_review,
        'monthly_review': monthly_review,
        'behavioral_insights': behavioral_insights,
        'voice_summary': voice_summary,
    }
