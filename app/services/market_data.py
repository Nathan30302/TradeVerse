"""
Market data service (live-first with safe fallback).

The system centralizes quote retrieval to keep consistent pricing across UI.
Providers:
- Twelve Data (multi-asset): requires TWELVEDATA_API_KEY

Caching:
- In-memory TTL cache (process-local). Can be swapped for Redis later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import os
import time

import requests


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float
    open_price: Optional[float]
    prev_close: Optional[float]
    change_pct: float
    ts: float


def _utcnow_ts() -> float:
    return time.time()


class _TTLCache:
    def __init__(self):
        self._data: Dict[str, Tuple[float, Quote]] = {}

    def get(self, key: str) -> Optional[Quote]:
        v = self._data.get(key)
        if not v:
            return None
        exp, q = v
        if _utcnow_ts() > exp:
            self._data.pop(key, None)
            return None
        return q

    def set(self, key: str, quote: Quote, ttl_s: int) -> None:
        self._data[key] = (_utcnow_ts() + ttl_s, quote)


_cache = _TTLCache()


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip()


def _twelvedata_symbol(symbol: str) -> str:
    """
    Map internal symbols to Twelve Data symbols.
    Minimal mapping for the app's featured instruments.
    """
    s = _normalize_symbol(symbol)
    mapping = {
        "EURUSD": "EUR/USD",
        "XAUUSD": "XAU/USD",
        "BTCUSD": "BTC/USD",
        "US500": "SPX",  # S&P 500 index proxy (varies by provider)
        "US30": "DJI",   # Dow proxy
        "NAS100": "NDX", # Nasdaq 100 proxy
    }
    return mapping.get(s, s)


def _quote_from_twelvedata(symbol: str, *, api_key: str, timeout_s: int = 6) -> Quote:
    td_symbol = _twelvedata_symbol(symbol)
    # Use quote endpoint (real-time-ish) + previous close if available.
    # Docs: https://twelvedata.com/docs
    url = "https://api.twelvedata.com/quote"
    resp = requests.get(url, params={"symbol": td_symbol, "apikey": api_key}, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json() or {}
    if data.get("status") == "error":
        raise RuntimeError(data.get("message") or "twelvedata_error")

    price = float(data["price"])
    open_price = float(data["open"]) if data.get("open") not in (None, "") else None
    prev_close = float(data["previous_close"]) if data.get("previous_close") not in (None, "") else None
    name = data.get("name") or _normalize_symbol(symbol)

    base = open_price or prev_close
    change_pct = 0.0
    if base and base != 0:
        change_pct = (price - base) / base * 100.0

    return Quote(
        symbol=_normalize_symbol(symbol),
        name=str(name),
        price=price,
        open_price=open_price,
        prev_close=prev_close,
        change_pct=float(round(change_pct, 4)),
        ts=_utcnow_ts(),
    )


def get_quotes(symbols: List[str], *, ttl_s: int = 10) -> List[Quote]:
    """
    Live-first quotes.
    In production: requires a configured provider.
    In development: falls back to the simulated market if provider is missing.
    """
    symbols_n = [_normalize_symbol(s) for s in symbols if s]
    if not symbols_n:
        return []

    provider = (os.environ.get("MARKET_DATA_PROVIDER") or "twelvedata").lower()
    is_production = (os.environ.get("FLASK_ENV") or "").lower() == "production"
    allow_sim_fallback = (os.environ.get("MARKET_DATA_ALLOW_SIM_FALLBACK") or "").lower() in ("1", "true", "yes")

    out: List[Quote] = []
    missing: List[str] = []
    for sym in symbols_n:
        cached = _cache.get(f"q:{provider}:{sym}")
        if cached:
            out.append(cached)
        else:
            missing.append(sym)

    if missing:
        if provider == "twelvedata":
            api_key = os.environ.get("TWELVEDATA_API_KEY", "")
            if not api_key:
                if is_production and not allow_sim_fallback:
                    raise RuntimeError("TWELVEDATA_API_KEY missing")
                # fallback (dev or explicitly allowed in prod)
                from app.services.simulated_market import market

                quotes = market.get_quotes(missing)
                for q in quotes:
                    qt = Quote(
                        symbol=q["symbol"],
                        name=q.get("name") or q["symbol"],
                        price=float(q["price"]),
                        open_price=None,
                        prev_close=None,
                        change_pct=float(q.get("change_pct") or 0.0),
                        ts=_utcnow_ts(),
                    )
                    _cache.set(f"q:{provider}:{qt.symbol}", qt, ttl_s)
                    out.append(qt)
            else:
                for sym in missing:
                    qt = _quote_from_twelvedata(sym, api_key=api_key)
                    _cache.set(f"q:{provider}:{qt.symbol}", qt, ttl_s)
                    out.append(qt)
        else:
            raise RuntimeError(f"Unsupported MARKET_DATA_PROVIDER: {provider}")

    # Keep requested order
    idx = {s: i for i, s in enumerate(symbols_n)}
    out.sort(key=lambda q: idx.get(q.symbol, 1_000_000))
    return out

