"""
Lightweight signup abuse guards (per-IP rate limits).

In-memory counters are best-effort across multi-worker hosts; still stops
casual mass-registration from a single process / IP burst.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List

_lock = threading.Lock()
_hits: Dict[str, List[float]] = {}


def client_ip_from_request(request) -> str:
    """Best-effort client IP behind Render/Cloudflare proxies."""
    raw = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For")
        or request.remote_addr
        or ""
    )
    return (raw.split(",")[0].strip() if raw else "")[:64] or "unknown"


def register_rate_limited(ip: str, *, max_per_window: int, window_seconds: int) -> bool:
    """
    Return True if this IP should be blocked from registering again right now.

    Records a hit when returning False (allowed).
    """
    if max_per_window < 1 or window_seconds < 1:
        return False
    key = (ip or "unknown").strip() or "unknown"
    now = time.time()
    with _lock:
        recent = [t for t in _hits.get(key, []) if now - t < window_seconds]
        if len(recent) >= max_per_window:
            _hits[key] = recent
            return True
        recent.append(now)
        _hits[key] = recent
        # Bound map size
        if len(_hits) > 5000:
            stale = [k for k, v in _hits.items() if not v or now - v[-1] > window_seconds]
            for k in stale[:1000]:
                _hits.pop(k, None)
        return False


def reset_register_rate_limits() -> None:
    """Test helper."""
    with _lock:
        _hits.clear()
