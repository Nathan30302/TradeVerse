"""
PnL service (single source of truth).

TradeVerse currently has multiple historical PnL implementations. For production
stability, all persisted trade PnL and calculator APIs should share the same
logic and instrument metadata source.
"""

from __future__ import annotations

from typing import Tuple


def calculate_trade_pnl(
    *,
    symbol: str,
    trade_type: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    commission: float = 0.0,
    swap: float = 0.0,
) -> Tuple[float, float, str]:
    """
    Calculate PnL using the Exness-style calculator backed by DB instrument metadata.

    Returns:
        (pnl, pips_or_points, method)
    """
    from app.services.exness_pnl_calculator import calculate_pnl as exness_calculate_pnl

    return exness_calculate_pnl(
        symbol=symbol,
        trade_type=trade_type,
        entry_price=entry_price,
        exit_price=exit_price,
        lot_size=lot_size,
        commission=commission,
        swap=swap,
    )

