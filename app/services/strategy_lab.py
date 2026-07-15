"""
Strategy Lab — plain-English setup → structured rules → journal / demo backtest.

Full multi-year OHLC market backtesting (FVG/sweep chart overlays on 11y data)
is a separate data-pipeline product. This module ships:
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
    ('fvg', re.compile(r'\b(fvg|fair\s*value\s*gap|imbalance)\b', re.I)),
    ('sweep', re.compile(r'\b(sweep|liquidity\s*grab|stop\s*hunt|raid)\b', re.I)),
    ('bos', re.compile(r'\b(bos|break\s*of\s*structure|choch|change\s*of\s*character)\b', re.I)),
    ('ob', re.compile(r'\b(order\s*block|\bob\b)\b', re.I)),
    ('retest', re.compile(r'\b(retest|pullback|mitigation)\b', re.I)),
    ('session', re.compile(r'\b(london|new\s*york|ny\s*open|asian|killzone)\b', re.I)),
    ('trend', re.compile(r'\b(trend|htf|higher\s*time\s*frame|bias)\b', re.I)),
)


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
            # soft match: allow if symbol empty on rule
            if rules.symbol_hint and trade.symbol:
                return False
    if rules.direction_hint and (trade.trade_type or '').upper() != rules.direction_hint:
        return False
    # Prefer tagged strategy / notes that mention concepts
    blob = ' '.join(
        filter(
            None,
            [
                trade.strategy or '',
                trade.post_trade_notes or '',
                trade.lessons_learned or '',
                trade.emotion or '',
            ],
        )
    ).lower()
    if rules.concepts and rules.concepts != ['discretionary']:
        if any(c in blob for c in rules.concepts):
            return True
        # Still include symbol/direction-matched closed trades as candidates
        return bool(rules.symbol_hint or rules.direction_hint)
    return True


def _narrative_for_journal(trade: Trade, rules: ParsedRules) -> List[str]:
    lines = []
    concepts = rules.concepts
    if 'sweep' in concepts:
        lines.append(
            f"Sweep context: look for liquidity raid before {trade.trade_type} entry "
            f"near {trade.entry_price}."
        )
    if 'fvg' in concepts:
        lines.append(
            "FVG / imbalance: confirm price left a gap that price returned into before entry."
        )
    if 'bos' in concepts:
        lines.append("Structure: require break of structure in the trade direction first.")
    if 'retest' in concepts:
        lines.append("Retest: entry on return to broken level / mitigated zone.")
    if not lines:
        lines.append("Matched from your journal by symbol/direction/notes — review the chart manually.")
    if trade.stop_loss is not None:
        lines.append(f"Invalidation / SL logged at {trade.stop_loss}.")
    if trade.take_profit is not None:
        lines.append(f"Target / TP logged at {trade.take_profit}.")
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
            'Journal mode scores your logged trades against the setup language. '
            'It is not a multi-year OHLC market backtest — that engine is next.'
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
                '1) Sweep: liquidity taken beyond prior swing.',
                '2) FVG: displacement leaves an imbalance.',
                '3) Entry: rebalance into FVG with confirmation candle.',
                '4) Invalidation: close beyond swept extreme.',
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
                '1) Sweep present but shallow.',
                '2) FVG filled mid-way — entry early.',
                '3) Structure failed; stop hit at invalidation.',
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
                '1) HTF bias aligned.',
                '2) Sweep + BOS in session window.',
                '3) Entry on FVG retest; partial at 1R, runner to target.',
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
            'Demo mode shows how annotated setups will look. '
            'Live multi-year market data + chart drawings ship in a later release.'
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
    mode: auto | journal | demo
    auto uses journal when matches exist, else demo.
    """
    rules = parse_plain_english_setup(description, symbol=symbol, timeframe=timeframe)
    mode = (mode or 'auto').lower()
    if mode == 'demo':
        result = run_demo_backtest(rules)
    elif mode == 'journal':
        result = run_journal_backtest(user_id, rules)
    else:
        result = run_journal_backtest(user_id, rules)
        if not result['trades']:
            demo = run_demo_backtest(rules)
            demo['fallback_from'] = 'journal_empty'
            demo['disclaimer'] = (
                'No matching journal trades yet — showing a demo annotation so you can '
                'see the format. Log tagged trades or import history to score your real edge.'
            )
            result = demo
    result['generated_at'] = datetime.now(timezone.utc).isoformat()
    return result


# Starter playbook templates (no migration — creates PlaybookSetup rows)
PLAYBOOK_STARTERS: List[Dict[str, Any]] = [
    {
        'key': 'london_fvg',
        'name': 'London FVG continuation (A+)',
        'market': 'Forex / Metals',
        'symbol_hint': 'XAUUSD',
        'timeframe': '15M',
        'entry_criteria': (
            'HTF bullish/bearish bias.\n'
            'London killzone: sweep of prior liquidity, then displacement leaving an FVG.\n'
            'Enter on rebalance into FVG with confirmation candle.'
        ),
        'invalidation': 'Candle close beyond the swept extreme / opposite side of FVG.',
        'management_plan': 'Partial at 1R, move SL to BE, trail under structure.',
        'checklist_text': '\n'.join(
            [
                'HTF bias clear',
                'Liquidity sweep occurred',
                'Displacement + FVG present',
                'Entry inside FVG / retest',
                'SL beyond invalidation',
                'No high-impact news in window',
            ]
        ),
        'tags': 'fvg,sweep,london,a+',
    },
    {
        'key': 'ny_bos_retest',
        'name': 'NY open BOS retest',
        'market': 'Indices',
        'symbol_hint': 'NAS100',
        'timeframe': '5M',
        'entry_criteria': (
            'Asia range mapped.\n'
            'NY open breaks structure (BOS) with momentum.\n'
            'Enter on first clean retest of broken level.'
        ),
        'invalidation': 'Failure to hold BOS level; close back inside prior range.',
        'management_plan': 'Scale 50% at 1.5R; runner to session high/low.',
        'checklist_text': '\n'.join(
            [
                'Asia range marked',
                'BOS confirmed',
                'Retest holds',
                'Risk ≤ 0.5% account',
                'Max 2 trades this session',
            ]
        ),
        'tags': 'bos,retest,ny,indices',
    },
    {
        'key': 'asian_range_fade',
        'name': 'Asian range fade (selective)',
        'market': 'Forex',
        'symbol_hint': 'EURUSD',
        'timeframe': '1H',
        'entry_criteria': (
            'Clear Asian range.\n'
            'Fade false break that reclaims range with rejection wick.\n'
            'Only when ADX/volatility is quiet and no London expansion yet.'
        ),
        'invalidation': 'Accepted break and hold outside range.',
        'management_plan': 'Target opposite range side; scratch if mid-range stall.',
        'checklist_text': '\n'.join(
            [
                'Range well defined',
                'False break + reclaim',
                'No pending news',
                'Position size reduced (mean-reversion)',
            ]
        ),
        'tags': 'range,fade,asia',
    },
]
