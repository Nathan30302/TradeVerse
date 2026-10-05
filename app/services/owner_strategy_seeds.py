"""
Seeded owner strategies for Nathan's Rules Desk.

Strategy 1 — FX AlexG Core (FX majors / hybrid day-swing)
Strategy 2 — Vincent Desiano Break & Retest (NQ/ES / ChartAcademy)
"""

from __future__ import annotations

from typing import Any, Dict, List


FX_ALEXG_SLUG = "fx-alexg-break-retest"
VINCENT_BR_SLUG = "vincent-desiano-break-retest"


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
            "ritual": [
                {
                    "id": "r1",
                    "title": "Open the window",
                    "do": "Confirm clock is 01:00–10:30 EST. If not — stop. No charts-as-entertainment.",
                    "pass": "Inside the window (or honest unlock).",
                },
                {
                    "id": "r2",
                    "title": "Pick the pair",
                    "do": "Only approved majors / SPX500. Write the symbol.",
                    "pass": "Symbol is on the watchlist.",
                },
                {
                    "id": "r3",
                    "title": "HTF sync",
                    "do": "Weekly + Daily same bias, OR Daily + 4H same bias. Bodies only. If conflict — discard.",
                    "pass": "Two consecutive TFs agree. Write BULLISH or BEARISH.",
                },
                {
                    "id": "r4",
                    "title": "AOI location",
                    "do": "Price must be retesting a Weekly/Daily AOI (≥3 body touches, 5–60 pips). No mid-air.",
                    "pass": "You can point to the AOI box on the chart.",
                },
                {
                    "id": "r5",
                    "title": "Pattern + candle",
                    "do": "Break & Retest or H&S neckline B&R, then engulfing / star / rejection on 15M–2H.",
                    "pass": "Pattern + candle both present in regime direction.",
                },
                {
                    "id": "r6",
                    "title": "Size & fire",
                    "do": "R:R ≥ 1:2. Lot from calculator. Market order with SL/TP. Then set-and-forget.",
                    "pass": "Order live with SL/TP — hands off.",
                },
            ],
            "practice": {
                "duration_minutes": 120,
                "title": "Daily 2-hour FX AlexG practice",
                "focus": "Train HTF sync + AOI patience. Become boring and profitable.",
                "blocks": [
                    {
                        "minutes": 25,
                        "title": "Top-down map (replay or live)",
                        "tasks": [
                            "On 3 pairs: mark Weekly HH/HL or LL/LH with bodies + Snake Trick.",
                            "Mark Daily the same way. Circle only pairs with W+D or D+4H sync.",
                            "Write one line bias per pair. Discard conflicts.",
                        ],
                    },
                    {
                        "minutes": 35,
                        "title": "AOI drills",
                        "tasks": [
                            "On synced pairs, draw Weekly/Daily AOIs inside active structure only.",
                            "Reject any zone <5 or >60 pips or with fewer than 3 body touches.",
                            "Screenshot 2 valid AOIs and 1 invalid — explain why.",
                        ],
                    },
                    {
                        "minutes": 40,
                        "title": "Entry trigger reps",
                        "tasks": [
                            "Replay or watch for Break & Retest into AOI — do NOT chase the break.",
                            "Mark 5 historical B&R candles (engulfing / morning-evening star).",
                            "Run 1–3 screenshots through Setup Coach before any sim entry.",
                        ],
                    },
                    {
                        "minutes": 20,
                        "title": "Risk & review",
                        "tasks": [
                            "Practice lot calc on 3 fake SL distances.",
                            "Journal: one rule you almost broke; one clean no-trade you took.",
                            "If you already have a win today — stop. Protect the edge.",
                        ],
                    },
                ],
            },
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


def vincent_desiano_strategy_payload() -> Dict[str, Any]:
    """Strategy 2 — Vincent Desiano / ChartAcademy Break & Retest (futures & equities)."""
    return {
        "slug": VINCENT_BR_SLUG,
        "name": "Break & Retest (Vincent Desiano)",
        "tagline": "ChartAcademy · 4-step continuation · PDH/PDL + DMA levels · 10-2-2 risk",
        "style": "Full-time day trader · Trend continuation",
        "overview": (
            "Vincent Desiano (ChartAcademy) Break and Retest: a 4-step trend-continuation system. "
            "Map key levels pre-market with zero discretion (PDH, PDL, Pre-Market High/Low, "
            "20/50/100/200 DMAs, major pivots). Trade clean breaks that return to retest the "
            "broken level as support/resistance, confirmed by price action and inter-market "
            "alignment (NQ↔ES or QQQ↔SPY). Avoid chop, tight consolidation, and divergence traps. "
            "Empirical edge: levels respected ~65–70%; valid B&R continues ~60–65%. "
            "Risk via 10-2-2 (≤10% capital allocation × ≤20% option premium loss = ≤2% account risk). "
            "Never chase unretested breaks. Never widen stops. Minimum 2R before full exit; scale out and leave runners."
        ),
        "markets": (
            "Futures: NQ, ES. Equities/options: QQQ, SPY, liquid names (NBIS, AMD, TSLA). "
            "Compare NQ vs ES and QQQ vs SPY for correlation / divergence traps."
        ),
        "instruments": [
            "NQ",
            "ES",
            "QQQ",
            "SPY",
            "NBIS",
            "AMD",
            "TSLA",
        ],
        "timeframes": "W → D → 4H → 1H (level map) · RTH execution (price-action confirmation)",
        "timezone_name": "America/New_York",
        "session_windows": [
            {
                "label": "Pre-market levels (EST)",
                "days": [0, 1, 2, 3, 4],
                "start": "04:00",
                "end": "09:30",
            },
            {
                "label": "RTH execution (EST)",
                "days": [0, 1, 2, 3, 4],
                "start": "09:30",
                "end": "16:00",
            },
        ],
        "weekly_bias_rules": (
            "Top-down: Weekly chart first — mark major pivots and rejection zones.\n"
            "Build visual zones between major rejection points; shade tight pivot clusters as No-Trade Zones.\n"
            "Prefer strong trending context; avoid weekly chop / conflicting structure."
        ),
        "daily_bias_rules": (
            "Daily map (mandatory, zero discretion):\n"
            "• Previous Day High (PDH) & Previous Day Low (PDL)\n"
            "• Pre-Market High & Pre-Market Low\n"
            "• Daily MAs: 20 / 50 / 100 / 200 DMA as dynamic areas of interest\n"
            "Identify rejection points and tight pivot No-Trade Zones before the open."
        ),
        "h4_rules": (
            "4H and 1H refine major pivots and rejection zones into actionable levels.\n"
            "Confirm the break / retest location still sits on a mapped HTF level — not a mid-air pivot.\n"
            "If price is inside a shaded No-Trade Zone between tight rejections → ABORT."
        ),
        "m15_rules": (
            "Intra-day confirmation is price-action at the retest (hold/reject), not a fixed LTF indicator stack.\n"
            "State tracker: Approaching Level → Breakout → Retest in Progress → Confirmed.\n"
            "Do NOT enter on the break alone — wait for the retest hold.\n"
            "Cross-check NQ/ES or QQQ/SPY alignment before pulling the trigger."
        ),
        "entry_rules": (
            "LONG:\n"
            "1) Clean break ABOVE key resistance (PDH / Pre-Market High / DMA).\n"
            "2) Pullback retests the broken level as new support.\n"
            "3) Price action confirms hold at the level.\n"
            "4) Cross-market aligned (no bull-trap divergence).\n"
            "5) Outside No-Trade Zones. Size with 10-2-2. Min 2R path.\n\n"
            "SHORT:\n"
            "1) Clean break BELOW key support (PDL / Pre-Market Low / DMA).\n"
            "2) Rally retests as new resistance.\n"
            "3) Price action confirms rejection.\n"
            "4) Markets aligned OR a valid divergence short setup.\n"
            "5) Outside No-Trade Zones. 10-2-2 size. Min 2R."
        ),
        "exit_rules": (
            "Stop beyond the retest key level.\n"
            "Default: candle close beyond the level exits.\n"
            "Aggressive override: immediate exit on violent adverse spike through the level.\n"
            "NEVER move / widen stops after entry.\n"
            "Scale out partials into strength; hold runners for extended gains.\n"
            "Minimum 2R before closing the full position."
        ),
        "invalidation_rules": (
            "Candle close (or violent spike) through the retest level against the trade.\n"
            "Inter-market divergence flips into a trap against your bias.\n"
            "Price slips into a No-Trade Zone — abort new adds."
        ),
        "do_not_trade_rules": (
            "Chase a breakout that has NOT retested.\n"
            "FOMO entry without a mapped level setup.\n"
            "Trade inside shaded No-Trade Zones (tight rejection clusters).\n"
            "Choppy markets / tight consolidation / conflicting inter-market divergences (as abort).\n"
            "Position size exceeding 10-2-2 limits (10% allocation / 20% option loss / 2% account).\n"
            "Moving stop losses wider after entry.\n"
            "Misidentified levels (trading off non-mapped pivots)."
        ),
        "psychology_rules": (
            "Audit every trade against the 5 Key Hurdles:\n"
            "1) Chasing breaks\n"
            "2) FOMO entries\n"
            "3) Misidentified levels\n"
            "4) Stop-loss modifications (widening)\n"
            "5) Early exit before 2R without technical reason\n"
            "Log violations. Pre-market map is mandatory — zero discretion on key levels.\n"
            "Strong trends only; sit out chop."
        ),
        "max_trades_per_day": 3,
        "stop_after_first_win": False,
        "max_losses_in_row": 2,
        "risk_base_pct": 2.0,
        "risk_min_pct": 0.5,
        "min_rr": 2.0,
        "target_rr": 3.0,
        "gate_strict": True,
        "checklist": {
            "pre_trade": [
                {"id": "levels", "label": "PDH, PDL, Pre-Market H/L, and 20/50/100/200 DMAs plotted"},
                {"id": "mtf", "label": "Rejection zones defined on Weekly, Daily, 4H, and 1H"},
                {"id": "break_retest", "label": "Price broke the level AND returned to retest (no chase)"},
                {"id": "pa", "label": "Price action holding/rejecting at the retest level"},
                {"id": "corr", "label": "NQ/ES or SPY/QQQ aligned — no conflicting trap"},
                {"id": "ntz", "label": "Entry clear of shaded No-Trade Zones"},
                {"id": "ten_two_two", "label": "10-2-2 risk: ≤10% allocation, ≤20% option loss, ≤2% account"},
                {"id": "delta", "label": "Options Delta evaluated for expected premium loss (if options)"},
                {"id": "rr", "label": "Path offers at least 2R before full exit"},
                {"id": "sl_fixed", "label": "SL beyond retest level — locked, never widen"},
            ],
            "no_trade": [
                {"id": "chase", "label": "Break without retest — do not chase"},
                {"id": "ntz", "label": "Inside No-Trade Zone between tight rejections"},
                {"id": "divergence", "label": "Inter-market divergence trap against bias"},
                {"id": "oversize", "label": "Size exceeds 10-2-2 limits"},
                {"id": "chop", "label": "Choppy / tight consolidation market"},
                {"id": "fomo", "label": "FOMO entry without mapped level"},
                {"id": "widen_sl", "label": "Tempted to widen stop after entry"},
            ],
            "states": [
                {"id": "premarket", "title": "Pre-market map", "prompt": "PDH/PDL, PMH/PML, DMAs, No-Trade Zones plotted?"},
                {"id": "approach", "title": "Approaching level", "prompt": "Price nearing a mapped key level?"},
                {"id": "breakout", "title": "Breakout", "prompt": "Clean break of the level (not a wick fake)?"},
                {"id": "retest", "title": "Retest in progress", "prompt": "Price returned to retest the broken level?"},
                {"id": "confirm", "title": "Confirmed", "prompt": "PA hold/reject + correlation OK + 10-2-2 sized?"},
                {"id": "manage", "title": "Manage", "prompt": "SL locked · scale into strength · runners for extension."},
            ],
            "hurdles": [
                {"id": "chase", "label": "Chasing breaks"},
                {"id": "fomo", "label": "FOMO entries"},
                {"id": "bad_level", "label": "Misidentified levels"},
                {"id": "widen_sl", "label": "Stop-loss modifications"},
                {"id": "early_exit", "label": "Early exit before 2R"},
            ],
            "ritual": [
                {
                    "id": "v1",
                    "title": "Pre-market map",
                    "do": "Plot PDH, PDL, Pre-Market High/Low, 20/50/100/200 DMA. Shade No-Trade Zones. Zero discretion.",
                    "pass": "All key levels are on the chart before RTH.",
                },
                {
                    "id": "v2",
                    "title": "Wait for the break",
                    "do": "Watch a mapped level break cleanly. Do not enter on the break.",
                    "pass": "Break happened on a mapped level — you are still flat.",
                },
                {
                    "id": "v3",
                    "title": "Wait for the retest",
                    "do": "Price returns to retest broken level as support (long) or resistance (short).",
                    "pass": "Retest is in progress at the level — not mid-air.",
                },
                {
                    "id": "v4",
                    "title": "Confirm PA + correlation",
                    "do": "Price action holds/rejects. Check NQ↔ES or QQQ↔SPY — abort traps.",
                    "pass": "Hold confirmed and markets aligned (or valid divergence short).",
                },
                {
                    "id": "v5",
                    "title": "10-2-2 then execute",
                    "do": "Size ≤10% allocation / ≤20% option loss / ≤2% account. SL beyond level — never widen. Min 2R.",
                    "pass": "Sized correctly, SL locked, path to 2R exists.",
                },
            ],
            "practice": {
                "duration_minutes": 120,
                "title": "Daily 2-hour Vincent B&R practice",
                "focus": "Levels first. Never chase. Correlation is a filter, not optional.",
                "blocks": [
                    {
                        "minutes": 25,
                        "title": "Pre-market mapping drill",
                        "tasks": [
                            "On NQ and ES (or QQQ/SPY): plot PDH/PDL, PMH/PML, DMAs before the open.",
                            "Shade at least one No-Trade Zone from tight pivots.",
                            "Screenshot your level map — compare to yesterday’s respect/fail.",
                        ],
                    },
                    {
                        "minutes": 40,
                        "title": "Break & retest replay",
                        "tasks": [
                            "Replay 8 historical sessions. Pause before the retest — call long, short, or pass.",
                            "Mark every chase you would have taken emotionally — then cross it out.",
                            "Track: would correlation have saved or aborted you?",
                        ],
                    },
                    {
                        "minutes": 35,
                        "title": "Live / sim RTH watch",
                        "tasks": [
                            "One A+ B&R only. Upload Daily + intraday screenshots to Setup Coach before entry.",
                            "If coach says wait — write the exact wait condition and sit on hands.",
                            "Practice 10-2-2 sizing on paper for any candidate.",
                        ],
                    },
                    {
                        "minutes": 20,
                        "title": "5 Hurdles review",
                        "tasks": [
                            "Score yourself on chasing, FOMO, bad levels, widened stops, early exits.",
                            "One paragraph: what made today a good no-trade (or a valid 2R path).",
                        ],
                    },
                ],
            },
        },
        "spec": {
            "system_name": "VINCENT_DESIANO_BREAK_RETEST",
            "instructor": "Vincent Desiano / ChartAcademy",
            "risk_model": "10-2-2",
            "allocation_pct_max": 10.0,
            "option_loss_pct_max": 20.0,
            "account_risk_pct_max": 2.0,
            "min_rr": 2.0,
            "level_respect_rate": "65-70%",
            "continuation_rate": "60-65%",
            "failure_rate": "35-40%",
            "correlation_pairs": [["NQ", "ES"], ["QQQ", "SPY"]],
            "stop_rule": "NEVER_WIDEN",
            "trade_management": "SCALE_OUT_AND_RUNNERS",
        },
    }


def all_strategy_payloads() -> List[Dict[str, Any]]:
    """Ordered seed list for the Rules Desk library."""
    return [
        fx_alexg_strategy_payload(),
        vincent_desiano_strategy_payload(),
    ]
