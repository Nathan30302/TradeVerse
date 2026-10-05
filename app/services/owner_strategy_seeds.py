"""
Seeded Strategy 1 — Break & Retest / FX AlexG Core Trading System.

Owner-only. Structured for the Rules Desk checklist state machine.
"""

from __future__ import annotations

from typing import Any, Dict


FX_ALEXG_SLUG = "fx-alexg-break-retest"


def fx_alexg_strategy_payload() -> Dict[str, Any]:
    """Full Strategy 1 definition for Nathan's Rules Desk."""
    return {
        "slug": FX_ALEXG_SLUG,
        "name": "Break & Retest (FX AlexG Core)",
        "tagline": "Hybrid day/swing · pro-trend · Weekly→Daily→4H sync · AOI break & retest",
        "style": "Hybrid Day + Swing · Trend-following",
        "overview": (
            "Hybrid day and swing trader. Identify trend on Weekly, Daily, and 4H using "
            "candlestick bodies only (Snake Trick for true HL/LH). Trade only when at least "
            "two consecutive timeframes are in sync (Weekly+Daily OR Daily+4H). Mark Areas of "
            "Interest on Weekly/Daily (3+ body touches, 5–60 pips, inside active HH–HL or LL–LH). "
            "Enter on Break & Retest or Head & Shoulders neckline B&R with engulfing / morning-evening "
            "star confirmation on 15M–2H. Session: 01:00–10:30 EST. Max two trades per day; "
            "stop after the first win. Set-and-forget; minimum 1:2 R:R (target 1:4)."
        ),
        "markets": (
            "EURUSD, GBPUSD, AUDCAD, NZDUSD, USDJPY, USDCAD, USDCHF, GBPCHF, SPX500 "
            "(also watch indices, commodities, crypto — primary edge is FX majors)"
        ),
        "instruments": [
            "EURUSD",
            "GBPUSD",
            "AUDCAD",
            "NZDUSD",
            "USDJPY",
            "USDCAD",
            "USDCHF",
            "GBPCHF",
            "SPX500",
        ],
        "timeframes": "W, D, 4H (trend/AOI) · 2H, 1H, 30M, 15M (entry)",
        "timezone_name": "America/New_York",
        "session_windows": [
            {
                "label": "Active execution (EST)",
                "days": [0, 1, 2, 3, 4],
                "start": "01:00",
                "end": "10:30",
            }
        ],
        "weekly_bias_rules": (
            "Identify Weekly trend with body closes only (ignore wicks for structure).\n"
            "Bullish = consecutive Higher Highs + Higher Lows.\n"
            "Bearish = consecutive Lower Lows + Lower Highs.\n"
            "Use Snake Trick: from extreme HH/LL head, trace backward to first significant body elbow "
            "to locate the true HL or LH.\n"
            "Structure shift ONLY when a candle BODY closes beyond the prior swing point."
        ),
        "daily_bias_rules": (
            "Map Daily HH/HL or LL/LH the same way (bodies only).\n"
            "Alignment gate: Weekly+Daily in sync OR Daily+4H in sync — otherwise NO TRADE.\n"
            "Example invalid: Weekly bullish while 4H bearish with no Daily bridge → discard pair.\n"
            "Draw Daily AOIs only inside the active structure bounds."
        ),
        "h4_rules": (
            "Confirm 4H structure aligns with the chosen regime when using Daily+4H sync.\n"
            "Do not invent a new bias on 4H against Weekly+Daily agreement.\n"
            "4H can refine timing but AOIs are owned by Weekly/Daily."
        ),
        "m15_rules": (
            "Entry confirmation on 15M / 30M / 1H / 2H only AFTER price is at a valid Weekly/Daily AOI.\n"
            "Bullish at support: Morning Star, Bullish Engulfing, Hammer/Doji rejection.\n"
            "Bearish at resistance: Evening Star, Bearish Engulfing, Shooting Star/Doji.\n"
            "No mid-air entries. No predicting absolute tops/bottoms."
        ),
        "entry_rules": (
            "1) Session 01:00–10:30 EST.\n"
            "2) Regime from synced HTFs — buys only in bullish regime, sells only in bearish.\n"
            "3) Price retesting valid Weekly/Daily AOI (≥3 body touches, 5–60 pips, sweet spot 20–35).\n"
            "4) Pattern: Break & Retest of AOI OR H&S / Inverse H&S neckline Break & Retest.\n"
            "5) Candlestick signal on 15M–2H.\n"
            "6) R:R ≥ 1:2 (prefer 1:4). Market instant execution only — no pending limits/stops.\n"
            "7) Lot size from calculator: Balance × Risk% / (SL pips × pip value). SL always set."
        ),
        "exit_rules": (
            "Set and forget — do not emotionally close early.\n"
            "Allow SL or TP to hit. Partials OK if lot > 0.01.\n"
            "SL beyond rejection wick / structural swing. TP at ≥1:2 or opposite major AOI.\n"
            "Update SL only when a new structural swing confirms."
        ),
        "invalidation_rules": (
            "Body close back through AOI / neckline against the trade.\n"
            "HTF sync breaks (conflict appears).\n"
            "Outside session — no new entries after 10:30 EST."
        ),
        "do_not_trade_rules": (
            "Outside 01:00–10:30 EST (Sydney/Tokyo dead zone).\n"
            "HTFs not consecutively synced.\n"
            "Price mid-air (not at Weekly/Daily AOI).\n"
            "Buying into resistance or selling into support.\n"
            "AOI <5 or >60 pips, or <3 body touches.\n"
            "Pending orders. R:R < 1:2.\n"
            "Red-folder news spike without plan.\n"
            "EMA alone, Fib, RSI, MACD, Bollinger, harmonics — discarded tools."
        ),
        "psychology_rules": (
            "Max 2 trades per day.\n"
            "If trade 1 is a WIN → DONE for the day.\n"
            "If trade 1 is a LOSS → one more opportunity only.\n"
            "If trade 2 finishes (win or loss) → DONE.\n"
            "No revenge. No full-port gambling on this desk (use 1% base risk; floor in drawdown).\n"
            "Log every plan violation."
        ),
        "max_trades_per_day": 2,
        "stop_after_first_win": True,
        "max_losses_in_row": 2,
        "risk_base_pct": 1.0,
        "risk_min_pct": 0.25,
        "min_rr": 2.0,
        "target_rr": 4.0,
        "gate_strict": True,
        "checklist": {
            "pre_trade": [
                {"id": "session", "label": "Time is between 01:00 and 10:30 AM EST"},
                {"id": "instrument", "label": "Instrument is on the approved FX / SPX500 watchlist"},
                {"id": "htf_sync", "label": "At least 2 consecutive HTFs in sync (W+D or D+4H)"},
                {"id": "aoi", "label": "Price retesting valid Weekly/Daily AOI (≥3 touches, 5–60 pips)"},
                {"id": "direction", "label": "Buying support (above) or selling resistance (below)"},
                {"id": "pattern", "label": "Break & Retest or H&S neckline Break & Retest present"},
                {"id": "candle", "label": "Entry candle signal on 15M–2H (engulfing / star / rejection)"},
                {"id": "rr", "label": "R:R ≥ 1:2 (target 1:4 when available)"},
                {"id": "lots", "label": "Lot size calculated from balance, risk %, and SL pips"},
                {"id": "sl_tp", "label": "Market order with pre-set SL and TP (no pendings)"},
            ],
            "no_trade": [
                {"id": "off_hours", "label": "Outside 01:00–10:30 EST"},
                {"id": "conflict", "label": "Higher timeframes conflicting"},
                {"id": "midair", "label": "Price not at a Weekly/Daily AOI"},
                {"id": "wrong_side", "label": "Buying resistance or selling support"},
                {"id": "bad_aoi", "label": "AOI size/touches invalid"},
                {"id": "pending", "label": "Trying to use pending limit/stop"},
                {"id": "low_rr", "label": "R:R below 1:2"},
                {"id": "news", "label": "Blind entry into red-folder spike"},
            ],
            "states": [
                {"id": "idle", "title": "Session gate", "prompt": "Are you inside 01:00–10:30 EST?"},
                {"id": "align", "title": "HTF alignment", "prompt": "Weekly+Daily or Daily+4H synced?"},
                {"id": "aoi", "title": "AOI scan", "prompt": "Valid Weekly/Daily AOI under price?"},
                {"id": "pattern", "title": "Pattern", "prompt": "Break & Retest or H&S neckline B&R?"},
                {"id": "signal", "title": "Entry signal", "prompt": "15M–2H candle confirmation + R:R ≥ 1:2?"},
                {"id": "execute", "title": "Execute", "prompt": "Market order sized, SL/TP set, then set-and-forget."},
            ],
        },
        "spec": {
            "system_name": "FX_ALEXG_CORE_TRADING_SYSTEM",
            "candle_evaluation_rule": "CANDLE_BODY_CLOSE_ONLY",
            "aoi_min_touches": 3,
            "aoi_min_pips": 5.0,
            "aoi_max_pips": 60.0,
            "execution_type": "MARKET_INSTANT_EXECUTION_ONLY",
            "trade_management": "SET_AND_FORGET",
        },
    }
