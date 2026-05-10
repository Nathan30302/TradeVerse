"""
Display-time FX: TradeVerse stores P/L and aggregates in USD-equivalent units.

For dashboards we convert to the user's preferred_currency using cached ECB-based
rates from the Frankfurter API (no API key). Falls back to 1:1 USD if fetch fails.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

_LOCK = threading.Lock()
_CACHE: Dict[str, object] = {"rates": None, "ts": 0.0}
_CACHE_TTL_SEC = 3600

FRANKFURTER_LATEST = "https://api.frankfurter.app/latest"

# ISO codes we allow in settings / filters (3 letters)
TARGET_CCYS = "EUR,GBP,JPY,CHF,AUD,CAD,NZD,ZAR"


def _fetch_usd_rates() -> Optional[Dict[str, float]]:
    """Return map currency_code -> units per 1 USD (e.g. ZAR ~ 18.5)."""
    url = f"{FRANKFURTER_LATEST}?from=USD&to={TARGET_CCYS}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradeVerse/2.0 (FX display)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rates = payload.get("rates") or {}
        out: Dict[str, float] = {}
        for k, v in rates.items():
            try:
                out[str(k).upper()] = float(v)
            except (TypeError, ValueError):
                continue
        out["USD"] = 1.0
        return out if out else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def get_usd_rates_map() -> Dict[str, float]:
    """Cached USD-based rates; stale cache kept on transient failures."""
    now = time.time()
    with _LOCK:
        cached = _CACHE.get("rates")
        ts = float(_CACHE.get("ts") or 0)
        if isinstance(cached, dict) and cached and now - ts < _CACHE_TTL_SEC:
            return dict(cached)

    fresh = _fetch_usd_rates()
    with _LOCK:
        if fresh:
            _CACHE["rates"] = fresh
            _CACHE["ts"] = time.time()
            return dict(fresh)
        if isinstance(_CACHE.get("rates"), dict) and _CACHE["rates"]:
            return dict(_CACHE["rates"])
        return {"USD": 1.0}


def usd_to_preferred_multiplier(target_currency: str) -> float:
    """Multiply a USD-equivalent amount to get display units in target_currency."""
    t = (target_currency or "USD").upper()
    if t == "USD":
        return 1.0
    rates = get_usd_rates_map()
    r = rates.get(t)
    if r is None:
        return 1.0
    return float(r)


def convert_usd_amount_for_display(amount: Optional[float], target_currency: str) -> float:
    """Convert stored USD-equivalent value to preferred currency (float)."""
    try:
        base = float(amount or 0)
    except (TypeError, ValueError):
        base = 0.0
    return base * usd_to_preferred_multiplier(target_currency)


CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CHF": "Fr",
    "AUD": "A$",
    "CAD": "C$",
    "NZD": "NZ$",
    "ZAR": "R",
}

# Settings dropdown labels (must match config DISPLAY_CURRENCIES)
DISPLAY_LABELS = {
    "USD": "USD ($)",
    "ZAR": "ZAR — South African Rand (R)",
    "EUR": "EUR (€)",
    "GBP": "GBP (£)",
    "JPY": "JPY (¥)",
    "CHF": "CHF (Fr)",
    "AUD": "AUD (A$)",
    "CAD": "CAD (C$)",
    "NZD": "NZD (NZ$)",
}


def format_converted_money(amount_usd: Optional[float], currency: str) -> str:
    """Format a USD-equivalent amount in the user's display currency."""
    try:
        base = float(amount_usd or 0)
    except (TypeError, ValueError):
        base = 0.0
    want = (currency or "USD").upper()
    rates = get_usd_rates_map()
    # Avoid misleading labels (e.g. R on raw USD) when FX feed is unavailable
    display_ccy = want if want == "USD" or want in rates else "USD"
    mult = float(rates[display_ccy]) if display_ccy != "USD" else 1.0
    val = base * mult
    sym = CURRENCY_SYMBOLS.get(display_ccy, "$")
    if display_ccy == "JPY":
        if val >= 0:
            return f"{sym}{val:,.0f}"
        return f"-{sym}{abs(val):,.0f}"
    if val >= 0:
        return f"{sym}{val:,.2f}"
    return f"-{sym}{abs(val):,.2f}"
