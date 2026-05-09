"""
Account-level flags for support / compliance (e.g. export hold).
"""

from __future__ import annotations


def current_user_exports_blocked(user) -> bool:
    """True if support has disabled CSV/data exports for this account."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        return bool(getattr(user, "exports_blocked", False))
    except Exception:
        return False
