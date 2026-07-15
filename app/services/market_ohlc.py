"""
OHLC market history for Strategy Lab backtesting.

Providers (in order after memory/disk cache):
1. Twelve Data — if TWELVEDATA_API_KEY is set
2. Yahoo Finance chart API — free daily OHLC
3. Frankfurter / ECB — free FX daily closes (high/low approximated)
4. Stooq daily CSV — best-effort

Successful downloads are written to disk (~24h) so Lab stays fast when Yahoo rate-limits.
Bars are daily by default (honest for free data). Intraday needs a paid feed.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests


@dataclass(frozen=True)
class OhlcBar:
    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float


_ohlc_cache: Dict[str, Tuple[float, List[OhlcBar], str]] = {}

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
}


def _normalize(symbol: str) -> str:
    return (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("=", "")


def _yahoo_symbol(symbol: str) -> Optional[str]:
    """Map TradeVerse journal symbols to Yahoo Finance tickers."""
    s = _normalize(symbol)
    mapping = {
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X",
        "NZDUSD": "NZDUSD=X",
        "EURGBP": "EURGBP=X",
        "EURJPY": "EURJPY=X",
        "GBPJPY": "GBPJPY=X",
        "XAUUSD": "GC=F",
        "GOLD": "GC=F",
        "XAGUSD": "SI=F",
        "SILVER": "SI=F",
        "BTCUSD": "BTC-USD",
        "BTC": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "ETH": "ETH-USD",
        "US500": "^GSPC",
        "SPX": "^GSPC",
        "SP500": "^GSPC",
        "US30": "^DJI",
        "DJ30": "^DJI",
        "NAS100": "^NDX",
        "NDX": "^NDX",
        "NASDAQ": "^NDX",
        "UK100": "^FTSE",
        "DE40": "^GDAXI",
        "WTI": "CL=F",
        "USOIL": "CL=F",
        "BRENT": "BZ=F",
    }
    if s in mapping:
        return mapping[s]
    if 1 <= len(s) <= 5 and s.isalpha():
        return s
    return None


def _stooq_symbol(symbol: str) -> Optional[str]:
    s = _normalize(symbol)
    mapping = {
        "EURUSD": "eurusd",
        "GBPUSD": "gbpusd",
        "USDJPY": "usdjpy",
        "AUDUSD": "audusd",
        "USDCAD": "usdcad",
        "USDCHF": "usdchf",
        "NZDUSD": "nzdusd",
        "XAUUSD": "xauusd",
        "BTCUSD": "btcusd",
        "NAS100": "^ndq",
        "US30": "^dji",
        "US500": "^spx",
    }
    return mapping.get(s)


def _twelvedata_symbol(symbol: str) -> str:
    s = _normalize(symbol)
    mapping = {
        "XAUUSD": "XAU/USD",
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "BTCUSD": "BTC/USD",
        "NAS100": "NDX",
        "US500": "SPX",
        "US30": "DJI",
    }
    return mapping.get(s, s)


def _frankfurter_pair(symbol: str) -> Optional[Tuple[str, str]]:
    """Return (base, quote) for ECB Frankfurter free FX history."""
    s = _normalize(symbol)
    if len(s) != 6 or not s.isalpha():
        return None
    base, quote = s[:3], s[3:]
    # Frankfurter does not quote every exotic; common majors work.
    return base, quote


def _disk_cache_dir() -> str:
    root = (
        (os.environ.get("TRADEVERSE_DATA_DIR") or "").strip()
        or (os.environ.get("PERSISTENT_DISK_PATH") or "").strip()
        or os.path.join("app", "static")
    )
    path = os.path.join(root, "uploads", "ohlc_cache")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.join("/tmp", "tradeverse_ohlc_cache")
        os.makedirs(path, exist_ok=True)
    return path


def _load_disk_cache(sym: str, *, max_age_s: int = 86400) -> Optional[Tuple[List[OhlcBar], str]]:
    path = os.path.join(_disk_cache_dir(), f"{sym}.json")
    try:
        if not os.path.isfile(path):
            return None
        if time.time() - os.path.getmtime(path) > max_age_s:
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        bars = [
            OhlcBar(
                date=str(b["date"]),
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
            )
            for b in (data.get("bars") or [])
        ]
        if len(bars) < 40:
            return None
        return bars, str(data.get("provider") or "disk")
    except Exception:
        return None


def _save_disk_cache(sym: str, bars: List[OhlcBar], provider: str) -> None:
    if not bars:
        return
    path = os.path.join(_disk_cache_dir(), f"{sym}.json")
    try:
        payload = {
            "provider": provider,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "bars": [asdict(b) for b in bars],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except Exception:
        pass


def _parse_stooq_csv(text: str) -> List[OhlcBar]:
    if not text or "<html" in text.lower()[:200]:
        return []
    reader = csv.DictReader(io.StringIO(text))
    bars: List[OhlcBar] = []
    for row in reader:
        try:
            day = (row.get("Date") or row.get("date") or "").strip()
            o = float(row.get("Open") or row.get("open"))
            h = float(row.get("High") or row.get("high"))
            low = float(row.get("Low") or row.get("low"))
            c = float(row.get("Close") or row.get("close"))
            bars.append(OhlcBar(date=day, open=o, high=h, low=low, close=c))
        except (TypeError, ValueError, KeyError):
            continue
    bars.sort(key=lambda b: b.date)
    return bars


def fetch_ohlc_yahoo(symbol: str, *, timeout_s: int = 15) -> List[OhlcBar]:
    ysym = _yahoo_symbol(symbol)
    if not ysym:
        return []
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}"
    resp = requests.get(
        url,
        params={"interval": "1d", "range": "1y"},
        timeout=timeout_s,
        headers=_UA,
    )
    if resp.status_code == 429:
        raise RuntimeError("yahoo_rate_limited")
    resp.raise_for_status()
    payload = resp.json() or {}
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return []
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    bars: List[OhlcBar] = []
    for i, ts in enumerate(timestamps):
        try:
            o, h, low, c = opens[i], highs[i], lows[i], closes[i]
            if o is None or h is None or low is None or c is None:
                continue
            day = time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
            bars.append(OhlcBar(date=day, open=float(o), high=float(h), low=float(low), close=float(c)))
        except (TypeError, ValueError, IndexError):
            continue
    bars.sort(key=lambda b: b.date)
    return bars


def fetch_ohlc_frankfurter(symbol: str, *, timeout_s: int = 12) -> List[OhlcBar]:
    """
    Free ECB FX history via Frankfurter. Only mid rates — we approximate
    OHLC from consecutive closes so support/resistance backtests still run.
    """
    pair = _frankfurter_pair(symbol)
    if not pair:
        return []
    base, quote = pair
    if base == quote:
        return []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=400)
    url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}"
    resp = requests.get(
        url,
        params={"from": base, "to": quote},
        timeout=timeout_s,
        headers=_UA,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    rates = data.get("rates") or {}
    if not rates:
        return []
    days = sorted(rates.keys())
    closes: List[Tuple[str, float]] = []
    for day in days:
        try:
            closes.append((day, float(rates[day][quote])))
        except (KeyError, TypeError, ValueError):
            continue
    bars: List[OhlcBar] = []
    prev = None
    for day, c in closes:
        o = prev if prev is not None else c
        # Synthetic range (~0.15%) so bounce/breakout heuristics have a wick.
        pad = abs(c) * 0.0015
        high = max(o, c) + pad
        low = min(o, c) - pad
        bars.append(OhlcBar(date=day, open=float(o), high=float(high), low=float(low), close=float(c)))
        prev = c
    return bars


def fetch_ohlc_stooq(symbol: str, *, timeout_s: int = 12) -> List[OhlcBar]:
    stooq = _stooq_symbol(symbol)
    if not stooq:
        return []
    for base in ("https://stooq.com/q/d/l/", "https://stooq.pl/q/d/l/"):
        try:
            resp = requests.get(
                base,
                params={"s": stooq, "i": "d"},
                timeout=timeout_s,
                headers=_UA,
            )
            if resp.status_code != 200:
                continue
            bars = _parse_stooq_csv(resp.text)
            if bars:
                return bars
        except Exception:
            continue
    return []


def fetch_ohlc_twelvedata(
    symbol: str,
    *,
    api_key: str,
    outputsize: int = 250,
    timeout_s: int = 12,
) -> List[OhlcBar]:
    url = "https://api.twelvedata.com/time_series"
    resp = requests.get(
        url,
        params={
            "symbol": _twelvedata_symbol(symbol),
            "interval": "1day",
            "outputsize": str(outputsize),
            "apikey": api_key,
            "order": "ASC",
        },
        timeout=timeout_s,
        headers=_UA,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    if data.get("status") == "error":
        raise RuntimeError(data.get("message") or "twelvedata_error")
    values = data.get("values") or []
    bars: List[OhlcBar] = []
    for row in values:
        try:
            bars.append(
                OhlcBar(
                    date=str(row["datetime"])[:10],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b.date)
    return bars


def fetch_daily_ohlc(symbol: str, *, limit: int = 250, ttl_s: int = 3600) -> Tuple[List[OhlcBar], str]:
    """
    Return (bars, provider_label). Memory + disk cache.
    Prefer Twelve Data when keyed, else Yahoo, else Frankfurter FX, else Stooq.
    """
    sym = _normalize(symbol)
    if not sym:
        return [], "none"
    cache_key = f"{sym}:{limit}"
    hit = _ohlc_cache.get(cache_key)
    now = time.time()
    if hit and hit[0] > now:
        return hit[1][-limit:], hit[2]

    disk = _load_disk_cache(sym)
    if disk:
        bars_d, prov_d = disk
        _ohlc_cache[cache_key] = (now + ttl_s, bars_d, prov_d)
        return bars_d[-limit:], prov_d

    bars: List[OhlcBar] = []
    provider = "none"
    api_key = (os.environ.get("TWELVEDATA_API_KEY") or os.environ.get("TWELVEDATA_KEY") or "").strip()
    if api_key:
        try:
            bars = fetch_ohlc_twelvedata(sym, api_key=api_key, outputsize=max(limit, 100))
            provider = "twelvedata"
        except Exception:
            bars = []

    if not bars:
        try:
            bars = fetch_ohlc_yahoo(sym)
            provider = "yahoo" if bars else "none"
        except Exception:
            bars = []
            provider = "none"

    if not bars:
        try:
            bars = fetch_ohlc_frankfurter(sym)
            provider = "frankfurter" if bars else "none"
        except Exception:
            bars = []
            provider = "none"

    if not bars:
        try:
            bars = fetch_ohlc_stooq(sym)
            provider = "stooq" if bars else "none"
        except Exception:
            bars = []
            provider = "none"

    if bars:
        _ohlc_cache[cache_key] = (now + ttl_s, bars, provider)
        _save_disk_cache(sym, bars, provider)
    return bars[-limit:], provider


def supports_symbol(symbol: str) -> bool:
    s = _normalize(symbol)
    if not s:
        return False
    if _yahoo_symbol(s):
        return True
    if _frankfurter_pair(s):
        return True
    if _stooq_symbol(s):
        return True
    if (os.environ.get("TWELVEDATA_API_KEY") or os.environ.get("TWELVEDATA_KEY") or "").strip():
        return True
    return False
