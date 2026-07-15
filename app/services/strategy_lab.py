"""
Strategy Lab — plain-English setup → structured rules → journal / demo backtest.

Market OHLC backtesting (daily Yahoo / optional Twelve Data) is available via
run_lab_backtest(mode='market'|'auto'). This module also ships:
1) rule extraction from English,
2) replay against the user's own journal trades,
3) a transparent demo run with annotated setup narratives.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import load_only

from app import db
from app.models.trade import Trade


CONCEPT_PATTERNS = (
    ('support', re.compile(r'\b(support|demand\s*zone|floor)\b', re.I)),
    ('resistance', re.compile(r'\b(resistance|supply\s*zone|ceiling)\b', re.I)),
    ('breakout', re.compile(r'\b(break\s*out|breakout|broke\s*(above|below)|acceptance)\b', re.I)),
    ('fvg', re.compile(r'\b(fvg|fair\s*value\s*gap|imbalance)\b', re.I)),
    ('sweep', re.compile(r'\b(sweep|liquidity\s*grab|stop\s*hunt|raid)\b', re.I)),
    ('bos', re.compile(r'\b(bos|break\s*of\s*structure|choch|change\s*of\s*character)\b', re.I)),
    ('ob', re.compile(r'\b(order\s*block|\bob\b)\b', re.I)),
    ('retest', re.compile(r'\b(retest|pullback|bounce|reject(ion)?|mitigation)\b', re.I)),
    ('session', re.compile(r'\b(london|new\s*york|ny\s*open|asian|killzone|session)\b', re.I)),
    ('trend', re.compile(r'\b(trend|htf|higher\s*time\s*frame|bias)\b', re.I)),
)

# Friendly labels for UI badges (jargon → everyday language)
CONCEPT_LABELS = {
    'support': 'Support (buy zone)',
    'resistance': 'Resistance (sell zone)',
    'breakout': 'Breakout',
    'fvg': 'Fair value gap (price gap)',
    'sweep': 'Liquidity sweep (stop run)',
    'bos': 'Break of structure',
    'ob': 'Order block',
    'retest': 'Retest / pullback',
    'session': 'Session timing',
    'trend': 'Trend / higher-timeframe bias',
    'discretionary': 'Discretionary (rules unclear)',
}

LAB_GLOSSARY = [
    ('Support', 'A price area where buyers often step in — price tends to bounce up from here.'),
    ('Resistance', 'A price area where sellers often step in — price tends to stall or reverse down.'),
    ('Breakout', 'Price pushes through support or resistance and stays beyond it.'),
    ('Retest', 'After a breakout or bounce, price returns to the level to confirm it still holds.'),
    ('Stop loss', 'Where you exit if the idea is wrong — protects the account.'),
    ('Take profit', 'Where you lock in gains — often the next clear level.'),
    ('Session', 'When the market is most active (London, New York, Asia).'),
    ('FVG / imbalance', 'A sharp move that leaves a “gap” on the chart; price often revisits it.'),
]

LAB_PRESETS = [
    {
        'label': 'Support bounce',
        'symbol': 'EURUSD',
        'timeframe': '1H',
        'description': (
            'On EURUSD 1-hour, wait for price to tap a clear support level with a rejection wick. '
            'Enter long on the bounce. Stop loss goes below support. Target the next resistance. '
            'Only trade when the higher timeframe bias is not strongly bearish.'
        ),
    },
    {
        'label': 'Resistance rejection',
        'symbol': 'XAUUSD',
        'timeframe': '15M',
        'description': (
            'On gold (XAUUSD) 15-minute during London, wait for price to hit resistance and reject '
            '(long upper wick). Enter short on confirmation. Stop above the wick high. '
            'Target the nearest support. Skip if high-impact news is due.'
        ),
    },
    {
        'label': 'Breakout + retest',
        'symbol': 'NAS100',
        'timeframe': '5M',
        'description': (
            'On NAS100 5-minute at New York open, wait for a breakout above resistance with momentum. '
            'Enter on the first clean retest of the broken level. Stop below the retest low. '
            'Take partial profits at 1.5R and let a runner go to the session high.'
        ),
    },
    {
        'label': 'Sweep → FVG (ICT)',
        'symbol': 'XAUUSD',
        'timeframe': '15M',
        'description': (
            'On XAUUSD 15M in London, wait for a liquidity sweep of the prior high or low, then a '
            'displacement that leaves an FVG. Enter on the retest of the FVG. '
            'Invalidation: close beyond the swept extreme.'
        ),
    },
]


@dataclass
class ParsedRules:
    concepts: List[str] = field(default_factory=list)
    direction_hint: Optional[str] = None  # BUY / SELL / None
    symbol_hint: Optional[str] = None
    timeframe_hint: Optional[str] = None
    entry_summary: str = ''
    invalidation_summary: str = ''
    raw: str = ''


@dataclass
class AnnotatedTrade:
    trade_id: Optional[int]
    symbol: str
    direction: str
    result: str  # win / loss / breakeven / demo
    pnl: Optional[float]
    entry_price: Optional[float]
    exit_price: Optional[float]
    narrative: List[str]
    concepts: List[str]
    source: str  # journal | demo


def parse_plain_english_setup(text: str, *, symbol: str = '', timeframe: str = '') -> ParsedRules:
    """Extract tradable concepts from a plain-English setup description."""
    raw = (text or '').strip()
    concepts = [name for name, pat in CONCEPT_PATTERNS if pat.search(raw)]
    direction = None
    if re.search(r'\b(long|buy|bullish)\b', raw, re.I):
        direction = 'BUY'
    elif re.search(r'\b(short|sell|bearish)\b', raw, re.I):
        direction = 'SELL'

    tf = timeframe.strip().upper() if timeframe else ''
    if not tf:
        m = re.search(r'\b(\d+\s*[mhMH]|1\s*H|4\s*H|15\s*M|5\s*M|1\s*D|daily|hourly)\b', raw)
        if m:
            tf = re.sub(r'\s+', '', m.group(1)).upper()

    sym = (symbol or '').strip().upper()
    if not sym:
        m = re.search(r'\b([A-Z]{3,10}(?:USD|USDT|JPY|GBP|EUR)?)\b', raw.upper())
        if m and m.group(1) not in {'FVG', 'BOS', 'CHOCH', 'HTF', 'LTF'}:
            sym = m.group(1)

    # Split rough entry / invalidation sentences
    entry = raw
    invalidation = ''
    for sep in ('Invalidation:', 'invalidation:', 'Stop if', 'I am wrong if', "I'm wrong if"):
        if sep in raw:
            parts = raw.split(sep, 1)
            entry = parts[0].strip()
            invalidation = parts[1].strip()
            break

    return ParsedRules(
        concepts=concepts or ['discretionary'],
        direction_hint=direction,
        symbol_hint=sym or None,
        timeframe_hint=tf or None,
        entry_summary=entry[:800],
        invalidation_summary=invalidation[:400],
        raw=raw,
    )


def _trade_matches_rules(trade: Trade, rules: ParsedRules) -> bool:
    if rules.symbol_hint:
        if (trade.symbol or '').upper() != rules.symbol_hint.upper():
            if rules.symbol_hint and trade.symbol:
                return False
    if rules.direction_hint and (trade.trade_type or '').upper() != rules.direction_hint:
        return False
    # Prefer tagged strategy / notes that mention concepts
    blob_parts = [
        trade.strategy or '',
        trade.pre_trade_plan or '',
        trade.post_trade_notes or '',
        trade.lessons_learned or '',
        trade.emotion or '',
    ]
    try:
        setup = getattr(trade, 'playbook_setup', None)
        if setup is not None:
            blob_parts.extend(
                [
                    getattr(setup, 'name', '') or '',
                    getattr(setup, 'tags', '') or '',
                    getattr(setup, 'entry_criteria', '') or '',
                    getattr(setup, 'checklist_text', '') or '',
                ]
            )
    except Exception:
        pass
    blob = ' '.join(filter(None, blob_parts)).lower()
    if rules.concepts and rules.concepts != ['discretionary']:
        if any(c in blob for c in rules.concepts):
            return True
        # Everyday synonyms in trader notes
        synonyms = {
            'support': ('support', 'demand', 'floor', 'bounce'),
            'resistance': ('resistance', 'supply', 'ceiling', 'reject'),
            'breakout': ('breakout', 'broke', 'break out'),
            'retest': ('retest', 'pullback', 'bounce'),
            'sweep': ('sweep', 'liquidity', 'stop hunt'),
            'fvg': ('fvg', 'imbalance', 'gap'),
            'session': ('london', 'new york', 'ny', 'asia', 'asian'),
        }
        for c in rules.concepts:
            for syn in synonyms.get(c, ()):
                if syn in blob:
                    return True
        return bool(rules.symbol_hint or rules.direction_hint)
    return True


def _narrative_for_journal(trade: Trade, rules: ParsedRules) -> List[str]:
    lines = []
    concepts = rules.concepts
    direction = (trade.trade_type or '').upper() or 'the'
    if 'support' in concepts:
        lines.append(
            f"Support: confirm price held a buy zone before the {direction} entry near {trade.entry_price}."
        )
    if 'resistance' in concepts:
        lines.append(
            f"Resistance: confirm price rejected a sell zone before the {direction} entry near {trade.entry_price}."
        )
    if 'breakout' in concepts:
        lines.append("Breakout: price should have pushed through a level and held beyond it.")
    if 'sweep' in concepts:
        lines.append(
            f"Liquidity sweep: look for a stop-run beyond a level, then reversal into the {direction} entry "
            f"near {trade.entry_price}."
        )
    if 'fvg' in concepts:
        lines.append(
            "Fair value gap: confirm a sharp move left a gap that price returned into before entry."
        )
    if 'bos' in concepts:
        lines.append("Structure shift: require a clear break of structure in the trade direction first.")
    if 'retest' in concepts:
        lines.append("Retest / pullback: entry on the return to the broken level or zone.")
    if 'session' in concepts:
        lines.append("Session: confirm this happened in your allowed window (e.g. London or New York).")
    if not lines:
        lines.append(
            "Matched from your journal by symbol, direction, or notes — open the trade and review the chart."
        )
    if trade.stop_loss is not None:
        lines.append(f"Your stop (where you're wrong) was logged at {trade.stop_loss}.")
    if trade.take_profit is not None:
        lines.append(f"Your target was logged at {trade.take_profit}.")
    return lines


def run_journal_backtest(
    user_id: int,
    rules: ParsedRules,
    *,
    limit: int = 40,
) -> Dict[str, Any]:
    """Score the described setup against the user's closed journal trades."""
    q = (
        Trade.query.options(
            load_only(
                Trade.id,
                Trade.symbol,
                Trade.trade_type,
                Trade.status,
                Trade.entry_price,
                Trade.exit_price,
                Trade.stop_loss,
                Trade.take_profit,
                Trade.profit_loss,
                Trade.strategy,
                Trade.pre_trade_plan,
                Trade.post_trade_notes,
                Trade.lessons_learned,
                Trade.emotion,
                Trade.entry_date,
                Trade.exit_date,
            )
        )
        .filter(Trade.user_id == user_id, Trade.status == 'CLOSED')
        .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
        .limit(200)
    )
    try:
        candidates = q.all()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        candidates = []

    matched: List[AnnotatedTrade] = []
    for t in candidates:
        if not _trade_matches_rules(t, rules):
            continue
        pnl = float(t.profit_loss) if t.profit_loss is not None else None
        if pnl is None:
            result = 'breakeven'
        elif pnl > 0:
            result = 'win'
        elif pnl < 0:
            result = 'loss'
        else:
            result = 'breakeven'
        matched.append(
            AnnotatedTrade(
                trade_id=t.id,
                symbol=t.symbol or '—',
                direction=(t.trade_type or '').upper() or '—',
                result=result,
                pnl=pnl,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                narrative=_narrative_for_journal(t, rules),
                concepts=list(rules.concepts),
                source='journal',
            )
        )
        if len(matched) >= limit:
            break

    wins = sum(1 for m in matched if m.result == 'win')
    losses = sum(1 for m in matched if m.result == 'loss')
    decided = wins + losses
    win_rate = (wins / decided * 100.0) if decided else 0.0
    net = sum((m.pnl or 0.0) for m in matched)

    return {
        'mode': 'journal',
        'rules': asdict(rules),
        'trades': [asdict(m) for m in matched],
        'stats': {
            'matched': len(matched),
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 1),
            'net_pnl': round(net, 2),
            'scanned': len(candidates),
        },
        'disclaimer': (
            'This scores trades you already logged against the words in your setup. '
            'It is not a full chart backtest on years of market candles yet — use it to check '
            'whether your real journal matches the idea.'
        ),
    }


def run_demo_backtest(rules: ParsedRules) -> Dict[str, Any]:
    """
    Annotated sample trades so users can see the product vision
    (sweep → FVG → entry) without waiting for market-data infra.
    """
    sym = rules.symbol_hint or 'XAUUSD'
    direction = rules.direction_hint or 'BUY'
    concepts = rules.concepts if rules.concepts != ['discretionary'] else ['sweep', 'fvg', 'retest']
    samples = [
        AnnotatedTrade(
            trade_id=None,
            symbol=sym,
            direction=direction,
            result='win',
            pnl=85.0,
            entry_price=2345.2 if direction == 'BUY' else 2362.5,
            exit_price=2358.0 if direction == 'BUY' else 2348.0,
            narrative=[
                '1) Trigger: price sweeps beyond a prior high/low (stops taken).',
                '2) Zone: a sharp move leaves a gap / imbalance.',
                '3) Entry: price returns into that zone with a confirmation candle.',
                '4) Stop: exit if price closes beyond the sweep extreme (idea is wrong).',
            ],
            concepts=concepts,
            source='demo',
        ),
        AnnotatedTrade(
            trade_id=None,
            symbol=sym,
            direction=direction,
            result='loss',
            pnl=-40.0,
            entry_price=2348.0 if direction == 'BUY' else 2355.0,
            exit_price=2340.0 if direction == 'BUY' else 2365.0,
            narrative=[
                '1) Trigger was weak — the sweep barely took liquidity.',
                '2) Entry came too early before the zone was respected.',
                '3) Level failed; stop hit — treat as a clean loss, not a revenge trade.',
            ],
            concepts=concepts,
            source='demo',
        ),
        AnnotatedTrade(
            trade_id=None,
            symbol=sym,
            direction=direction,
            result='win',
            pnl=120.0,
            entry_price=2338.5 if direction == 'BUY' else 2370.0,
            exit_price=2355.0 if direction == 'BUY' else 2348.0,
            narrative=[
                '1) Higher-timeframe bias agreed with the trade direction.',
                '2) Sweep + structure break happened in the planned session.',
                '3) Entry on the retest; banked part at 1R, left a runner to target.',
            ],
            concepts=concepts,
            source='demo',
        ),
    ]
    wins = sum(1 for m in samples if m.result == 'win')
    losses = sum(1 for m in samples if m.result == 'loss')
    return {
        'mode': 'demo',
        'rules': asdict(rules),
        'trades': [asdict(m) for m in samples],
        'stats': {
            'matched': len(samples),
            'wins': wins,
            'losses': losses,
            'win_rate': round(wins / max(1, wins + losses) * 100.0, 1),
            'net_pnl': round(sum(m.pnl or 0 for m in samples), 2),
            'scanned': len(samples),
        },
        'disclaimer': (
            'Demo examples show the format: trigger → level → entry → stop. '
            'When you log matching trades (or we add market-data backtesting), results use your real history.'
        ),
    }


def run_strategy_lab(
    user_id: int,
    description: str,
    *,
    symbol: str = '',
    timeframe: str = '',
    mode: str = 'auto',
) -> Dict[str, Any]:
    """
    mode: auto | journal | demo | market
    auto: market OHLC when symbol available, else journal matches, else demo.
    """
    rules = parse_plain_english_setup(description, symbol=symbol, timeframe=timeframe)
    mode = (mode or 'auto').lower()

    def _try_market() -> Optional[Dict[str, Any]]:
        try:
            from app.services.market_backtest import run_market_backtest
            from app.services.market_ohlc import supports_symbol

            sym = (rules.symbol_hint or symbol or '').strip()
            if not sym:
                return None
            if not supports_symbol(sym):
                # Still attempt — Yahoo may cover more than the static map
                pass
            return run_market_backtest(rules)
        except Exception:
            return None

    if mode == 'demo':
        result = run_demo_backtest(rules)
    elif mode == 'journal':
        result = run_journal_backtest(user_id, rules)
    elif mode == 'market':
        result = _try_market() or run_demo_backtest(rules)
        if result.get('mode') != 'market':
            result['fallback_from'] = 'market_unavailable'
            result['disclaimer'] = (
                'Market history unavailable for that symbol — showing demo format. '
                'Try EURUSD / XAUUSD, or set TWELVEDATA_API_KEY.'
            )
    else:
        # auto
        market = _try_market()
        if market and market.get('trades'):
            result = market
        else:
            result = run_journal_backtest(user_id, rules)
            if not result['trades']:
                if market and not market.get('trades'):
                    # Prefer market empty message if we attempted
                    demo = run_demo_backtest(rules)
                    demo['fallback_from'] = 'market_or_journal_empty'
                    demo['disclaimer'] = (
                        (market.get('disclaimer') if market else '')
                        + ' No journal matches either — showing demo annotations. '
                        'Log tagged trades or pick a liquid symbol (EURUSD, XAUUSD).'
                    )
                    result = demo
                else:
                    demo = run_demo_backtest(rules)
                    demo['fallback_from'] = 'journal_empty'
                    demo['disclaimer'] = (
                        'No matching journal trades yet — showing a demo annotation so you can '
                        'see the format. Use Market mode for daily OHLC backtests, or log tagged trades.'
                    )
                    result = demo
    result['generated_at'] = datetime.now(timezone.utc).isoformat()
    return result


# Starter playbook templates (no migration — creates PlaybookSetup rows)
PLAYBOOK_STARTERS: List[Dict[str, Any]] = [
    {
        'key': 'support_bounce',
        'name': 'Support bounce (A+)',
        'market': 'Forex / Metals',
        'symbol_hint': 'XAUUSD',
        'timeframe': '15M',
        'entry_criteria': (
            'Mark a clear support (buy zone) on your chart.\n'
            'Wait for price to tap support and reject (bounce wick).\n'
            'Enter long after confirmation. Prefer London or New York session.'
        ),
        'invalidation': 'Candle closes clearly below support — idea is wrong; exit.',
        'management_plan': 'Take partial profit at 1R, move stop to break-even, trail under higher lows.',
        'checklist_text': '\n'.join(
            [
                'Support level clearly marked',
                'Rejection / bounce at support',
                'Higher timeframe not strongly against you',
                'Stop placed below support',
                'Target at next resistance',
                'No high-impact news in the next hour',
            ]
        ),
        'tags': 'support,bounce,a+',
    },
    {
        'key': 'london_fvg',
        'name': 'London sweep → gap retest (A+)',
        'market': 'Forex / Metals',
        'symbol_hint': 'XAUUSD',
        'timeframe': '15M',
        'entry_criteria': (
            'Higher-timeframe bias agrees with the trade.\n'
            'During London: price sweeps stops beyond a level, then leaves a fair value gap.\n'
            'Enter when price returns into that gap with a confirmation candle.'
        ),
        'invalidation': 'Candle close beyond the sweep extreme (the idea failed).',
        'management_plan': 'Partial at 1R, move stop to break-even, trail under structure.',
        'checklist_text': '\n'.join(
            [
                'Higher-timeframe bias clear',
                'Liquidity sweep occurred',
                'Fair value gap present',
                'Entry on gap retest',
                'Stop beyond invalidation',
                'No high-impact news in window',
            ]
        ),
        'tags': 'fvg,sweep,london,a+',
    },
    {
        'key': 'ny_bos_retest',
        'name': 'NY breakout + retest',
        'market': 'Indices',
        'symbol_hint': 'NAS100',
        'timeframe': '5M',
        'entry_criteria': (
            'Mark the overnight / Asia range.\n'
            'At New York open, wait for a breakout through resistance (or support) with momentum.\n'
            'Enter on the first clean retest of the broken level.'
        ),
        'invalidation': 'Price fails to hold the breakout level and closes back inside the range.',
        'management_plan': 'Take 50% at 1.5R; let a runner go toward the session high/low.',
        'checklist_text': '\n'.join(
            [
                'Asia / overnight range marked',
                'Breakout confirmed',
                'Retest holds',
                'Risk ≤ 0.5% of account',
                'Max 2 trades this session',
            ]
        ),
        'tags': 'breakout,retest,ny,indices',
    },
    {
        'key': 'asian_range_fade',
        'name': 'Range fade at extremes',
        'market': 'Forex',
        'symbol_hint': 'EURUSD',
        'timeframe': '1H',
        'entry_criteria': (
            'Clear sideways range (support at bottom, resistance at top).\n'
            'Fade a false break that quickly reclaims the range with a rejection wick.\n'
            'Only when the market is quiet — skip if London is about to expand hard.'
        ),
        'invalidation': 'Price accepts and holds outside the range (true breakout).',
        'management_plan': 'Target the opposite side of the range; exit early if price stalls mid-range.',
        'checklist_text': '\n'.join(
            [
                'Range well defined (support + resistance)',
                'False break + reclaim',
                'No pending news',
                'Smaller size (mean-reversion risk)',
            ]
        ),
        'tags': 'range,support,resistance,asia',
    },
]
