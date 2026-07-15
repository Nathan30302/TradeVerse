"""
Simple rule-based OHLC backtester for Strategy Lab.

Uses daily bars (Yahoo free / ECB Frankfurter for FX / Twelve Data when keyed). Not a full ICT engine —
transparent support/resistance, breakout, and pullback rules so traders can
see expectancy before trusting a setup.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from app.services.market_ohlc import OhlcBar, fetch_daily_ohlc, supports_symbol
from app.services.strategy_lab import AnnotatedTrade, ParsedRules


def _lookback_low(bars: List[OhlcBar], i: int, n: int) -> float:
    window = bars[max(0, i - n) : i]
    return min(b.low for b in window) if window else bars[i].low


def _lookback_high(bars: List[OhlcBar], i: int, n: int) -> float:
    window = bars[max(0, i - n) : i]
    return max(b.high for b in window) if window else bars[i].high


def run_market_backtest(rules: ParsedRules, *, max_trades: int = 25) -> Dict[str, Any]:
    """
    Backtest plain-English concepts against daily OHLC.
    Risk model: 1R = distance to stop; target = 2R (fixed, transparent).
    """
    sym = (rules.symbol_hint or "").upper().strip() or "EURUSD"
    if not supports_symbol(sym) and not rules.symbol_hint:
        sym = "EURUSD"

    bars, provider = fetch_daily_ohlc(sym, limit=260)
    if len(bars) < 40:
        return {
            "mode": "market",
            "rules": asdict(rules),
            "trades": [],
            "stats": {
                "matched": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "scanned": len(bars),
            },
            "provider": provider,
            "symbol": sym,
            "disclaimer": (
                f"Could not load enough market history for {sym}. "
                "Try EURUSD/GBPUSD (ECB Frankfurter free FX), or set TWELVEDATA_API_KEY "
                "for gold/indices/crypto when Yahoo is rate-limited."
            ),
        }

    concepts = set(rules.concepts or [])
    prefer_long = rules.direction_hint != "SELL"
    prefer_short = rules.direction_hint != "BUY"
    # Default both if no direction
    if rules.direction_hint is None:
        prefer_long = prefer_short = True

    look = 10
    trades: List[AnnotatedTrade] = []
    i = look
    while i < len(bars) - 2 and len(trades) < max_trades:
        b = bars[i]
        support = _lookback_low(bars, i, look)
        resistance = _lookback_high(bars, i, look)
        risk_unit = max((resistance - support) * 0.15, abs(b.close) * 0.0015, 1e-6)

        entry = None
        direction = None
        stop = None
        narrative: List[str] = []

        # Support bounce (long)
        if prefer_long and (
            "support" in concepts
            or "retest" in concepts
            or concepts.intersection({"discretionary", "trend"})
            or not concepts.intersection({"resistance", "breakout", "sweep", "fvg"})
        ):
            near_support = b.low <= support * 1.0015 and b.close > support
            rejection = b.close > b.open and (b.high - b.close) < (b.close - b.low)
            if near_support and (rejection or "support" in concepts):
                entry = b.close
                direction = "BUY"
                stop = min(b.low, support) - risk_unit * 0.25
                narrative = [
                    f"1) Support zone from prior {look} days near {support:.5g}.",
                    f"2) Bounce / rejection candle on {b.date} (close {b.close:.5g}).",
                    "3) Entry at close; stop under the wick / support.",
                    "4) Target 2× risk (transparent fixed R model).",
                ]

        # Resistance rejection (short)
        if entry is None and prefer_short and ("resistance" in concepts or "retest" in concepts):
            near_res = b.high >= resistance * 0.9985 and b.close < resistance
            rejection = b.close < b.open and (b.close - b.low) < (b.high - b.close)
            if near_res and rejection:
                entry = b.close
                direction = "SELL"
                stop = max(b.high, resistance) + risk_unit * 0.25
                narrative = [
                    f"1) Resistance from prior {look} days near {resistance:.5g}.",
                    f"2) Rejection candle on {b.date}.",
                    "3) Short at close; stop above the wick / resistance.",
                    "4) Target 2× risk.",
                ]

        # Breakout long
        if entry is None and prefer_long and "breakout" in concepts:
            prior_high = _lookback_high(bars, i, look)
            if b.close > prior_high and b.close > b.open:
                entry = b.close
                direction = "BUY"
                stop = prior_high - risk_unit * 0.1
                narrative = [
                    f"1) Breakout above {look}-day high ({prior_high:.5g}).",
                    f"2) Close acceptance on {b.date}.",
                    "3) Stop just under the breakout level.",
                    "4) Target 2× risk.",
                ]

        # Breakout short
        if entry is None and prefer_short and "breakout" in concepts:
            prior_low = _lookback_low(bars, i, look)
            if b.close < prior_low and b.close < b.open:
                entry = b.close
                direction = "SELL"
                stop = prior_low + risk_unit * 0.1
                narrative = [
                    f"1) Breakdown below {look}-day low ({prior_low:.5g}).",
                    f"2) Close acceptance on {b.date}.",
                    "3) Stop just above the breakdown level.",
                    "4) Target 2× risk.",
                ]

        if entry is None or direction is None or stop is None:
            i += 1
            continue

        risk = abs(entry - stop)
        if risk <= 0:
            i += 1
            continue
        target = entry + 2 * risk if direction == "BUY" else entry - 2 * risk

        # Simulate forward until stop/target or 15 bars
        exit_price = bars[min(i + 15, len(bars) - 1)].close
        exit_date = bars[min(i + 15, len(bars) - 1)].date
        result = "breakeven"
        for j in range(i + 1, min(i + 16, len(bars))):
            nb = bars[j]
            if direction == "BUY":
                if nb.low <= stop:
                    exit_price = stop
                    exit_date = nb.date
                    result = "loss"
                    break
                if nb.high >= target:
                    exit_price = target
                    exit_date = nb.date
                    result = "win"
                    break
            else:
                if nb.high >= stop:
                    exit_price = stop
                    exit_date = nb.date
                    result = "loss"
                    break
                if nb.low <= target:
                    exit_price = target
                    exit_date = nb.date
                    result = "win"
                    break
        else:
            pnl_r = (exit_price - entry) / risk if direction == "BUY" else (entry - exit_price) / risk
            result = "win" if pnl_r > 0.15 else ("loss" if pnl_r < -0.15 else "breakeven")

        pnl_r = (exit_price - entry) / risk if direction == "BUY" else (entry - exit_price) / risk
        # Display P/L as R-multiples × 100 for readable demo units
        pnl_display = round(pnl_r * 100.0, 2)
        narrative.append(f"5) Exit {exit_date}: {result} ({pnl_r:+.2f}R).")

        trades.append(
            AnnotatedTrade(
                trade_id=None,
                symbol=sym,
                direction=direction,
                result=result,
                pnl=pnl_display,
                entry_price=round(entry, 5),
                exit_price=round(exit_price, 5),
                narrative=narrative,
                concepts=list(rules.concepts),
                source="market",
            )
        )
        i += 3  # skip overlap a bit

    wins = sum(1 for t in trades if t.result == "win")
    losses = sum(1 for t in trades if t.result == "loss")
    decided = wins + losses
    win_rate = (wins / decided * 100.0) if decided else 0.0
    net = sum((t.pnl or 0.0) for t in trades)

    provider_note = {
        "yahoo": "Yahoo Finance free daily history (no API key)",
        "stooq": "Stooq free daily history (no API key)",
        "frankfurter": "ECB Frankfurter free FX daily rates (synthetic high/low)",
        "twelvedata": "Twelve Data daily history (TWELVEDATA_API_KEY)",
        "disk": "Cached market history from a previous download",
        "none": "no provider",
    }.get(provider, provider)

    return {
        "mode": "market",
        "rules": asdict(rules),
        "trades": [asdict(t) for t in trades],
        "stats": {
            "matched": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "net_pnl": round(net, 2),
            "scanned": len(bars),
        },
        "provider": provider,
        "symbol": sym,
        "disclaimer": (
            f"Market backtest on daily candles via {provider_note}. "
            "P/L shown in synthetic units (100 ≈ 1R). This is a transparent rule check — "
            "not a guarantee of live results. For finer than daily (15M), add a paid feed key."
        ),
    }
