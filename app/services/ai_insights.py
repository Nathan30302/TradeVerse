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

    def answer_question(
        self,
        question: str,
        *,
        history: List[Dict[str, str]] | None = None,
        user_name: str = ''
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

        # Knowledge-base match (broad trading education), before stats-specific branches.
        kb = match_topic(text)
        if kb:
            kb_answer, kb_fups = render_topic(kb)
            # Add a tiny personalization footer when we have stats.
            if total > 0:
                kb_answer += f"\n\nYour current context: {total} closed trades, {win_rate:.0f}% win rate, avg R:R {avg_rr:.2f}."
            return {"answer": kb_answer, "follow_ups": kb_fups[:3]}

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
            return "\n".join(lines)

        # General trading knowledge topics (still tailored with your stats when possible)
        if has('risk', 'rr', 'r:r', 'risk reward', 'stop loss', 'sl', 'tp', 'take profit'):
            parts = [
                f"{user_name + ', ' if user_name else ''}here’s the clean way to think about risk and R-multiples:",
                "- Risk is what you lose if SL is hit (either in pips or $).",
                "- Reward is what you gain if TP is hit.",
                "- R:R is reward ÷ risk. Example: risking 1R to make 2R is 1:2.",
            ]
            if total > 0:
                parts.append(f"From your last week: average R:R ≈ {avg_rr:.2f}, win rate ≈ {win_rate:.0f}%, trades = {total}.")
                parts.append("If you raise R:R, you can stay profitable even with a lower win rate—but only if entries stay selective.")
            parts.append("If you want, tell me one recent trade (entry, SL, TP) and I’ll compute the exact R:R and what win rate you’d need.")
            answer = "\n".join(parts)
            return {'answer': answer, 'follow_ups': ["What’s my current weak point: win rate or R:R?", "Give me a stop-loss rule I can follow.", "How do I size positions safely?"]}

        if has('win rate', 'wins', 'losses', 'perform', 'performance', 'this week', 'weekly'):
            summary = weekly.get('summary') or ''
            if not summary:
                summary = f"Weekly snapshot: {total} closed trades, {win_rate:.0f}% win rate, net {total_pnl:.0f}, average R:R {avg_rr:.2f}."
            # Premium: structured coach brief with actions + evidence.
            answer = (
                "**Weekly Coach Brief**\n"
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
            return {'answer': answer, 'follow_ups': ["What’s my biggest leak this week?", "Give me one rule for next week.", "Build me a pre-trade checklist."]}

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
                return {'answer': "\n".join(lines), 'follow_ups': ["What’s my best session?", "What strategy wins most on my best day?", "How do I avoid forcing trades?"]}
            return {'answer': "I don’t have enough weekly trades to confidently rank days yet. Keep logging for another week and ask again.", 'follow_ups': ["What’s my weekly snapshot?", "What’s my biggest leak?"]}

        if has('best setup', 'best strategy', 'best', 'edge'):
            best = (setups or {}).get('best_strategy')
            if best and isinstance(best, dict):
                name = str(best.get('name') or '')
                wr = float(best.get('win_rate') or 0.0)
                count = int(best.get('total_trades') or 0)
                answer = f"Best strategy in your recent sample: **{name}** — {wr:.0f}% win rate over {count} trades."
                answer += "\n\nCoach note: double down only if you can describe the entry trigger in one sentence and repeat it."
                return {'answer': answer, 'follow_ups': [f"What are the conditions when {name} works best?", "What’s my worst strategy and why?", "Give me a checklist for this setup."]}
            return {'answer': "You don’t have a clear best setup yet (needs more tagged trades). Start tagging strategy consistently for the next 10 trades.", 'follow_ups': ["How should I tag strategies?", "What’s the fastest way to improve with low sample size?"]}

        if has('mistake', 'mistakes', 'leak', 'why am i losing', 'losing', 'overtrade', 'revenge', 'fomo'):
            issues = (alerts or [])[:4]
            if issues:
                answer = "Here are the top issues I can actually see in your recent sample:\n- " + "\n- ".join(issues)
            else:
                answer = (
                    "I don’t have strong alert signals yet, so here are the most common profit leaks to audit:\n"
                    "- Low R:R (taking 0.5R winners but 1R losers)\n"
                    "- Trading outside your best session\n"
                    "- Moving SL / closing winners early\n"
                    "- Revenge/FOMO entries\n"
                    "\nIf you tell me your last 3 losses, I’ll classify the leak."
                )
            if total > 0:
                answer += f"\n\nYour context: {total} trades, win rate {win_rate:.0f}%, avg R:R {avg_rr:.2f}."
            return {'answer': answer, 'follow_ups': ["What’s my one rule next week?", "How do I stop revenge trading?", "Build me a pre-trade checklist."]}

        if has('improve', 'get better', 'better trader', 'how can i', 'how do i improve', 'help me'):
            return {
                'answer': _coach_basics(),
                'follow_ups': [
                    "What’s my biggest leak this week?",
                    "Give me one rule for next week.",
                    "Build me a pre-trade checklist for my best setup.",
                ],
            }

        # Fallback: respond with a richer, non-repeating “coach brief” instead of the same summary
        base = weekly.get('summary') or f"Recent snapshot: {total} closed trades, {win_rate:.0f}% win rate, net {total_pnl:.0f}, avg R:R {avg_rr:.2f}."
        variations = [
            base,
            base + " If you want a sharper answer, ask about (1) best strategy, (2) biggest leak, or (3) next-week rule.",
            base + " Ask me a specific: ‘what should I stop doing?’ and I’ll give you one rule.",
        ]
        # Avoid exact repetition
        answer = next((v for v in variations if v != last_assistant), variations[0])

        # Light general knowledge supplement if user asked a broad trading question
        if re.search(r'\bhow do i\b|\bwhat is\b|\bexplain\b', text):
            answer += "\n\nIf your question is general trading knowledge, ask directly (e.g. “Explain liquidity”, “How to journal properly”, “How to manage drawdown”)."

        return {'answer': answer, 'follow_ups': ["Explain position sizing.", "What’s a good journaling process?", "What’s my best session?"]}
 
 
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
