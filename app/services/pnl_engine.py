"""
P&L Engine - Universal Profit/Loss Calculator

Calculates P&L for different asset classes:
- Forex: pip/tick conversion with lot size and currency conversion
- Indices: points * tick_value * contracts
- Commodities: contract_size * price_diff * multiplier
- Crypto: quantity * price_diff (or contract-based)
- Stocks: quantity * (exit - entry)
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, Literal
from decimal import Decimal, ROUND_HALF_UP

from app.services.instrument_catalog import get_instrument_metadata


@dataclass
class PnLResult:
    """Result of P&L calculation."""
    pnl: float
    pnl_currency: str
    pip_move: Optional[float]
    points: Optional[float]
    tick_move: Optional[float]
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pnl': self.pnl,
            'pnl_currency': self.pnl_currency,
            'pip_move': self.pip_move,
            'points': self.points,
            'tick_move': self.tick_move,
            'details': self.details
        }


class PnLEngine:
    """
    Universal P&L calculation engine supporting multiple asset classes.
    """
    
    @staticmethod
    def calculate(
        instrument_symbol: str,
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: Literal['lots', 'units', 'contracts'] = 'lots',
        trade_direction: Literal['buy', 'sell'] = 'buy',
        instrument_meta: Optional[Dict[str, Any]] = None,
        broker_profile: Optional[Dict[str, Any]] = None,
        account_currency: str = 'USD'
    ) -> PnLResult:
        """
        Calculate P&L for a trade.
        
        Args:
            instrument_symbol: The canonical instrument symbol
            entry_price: Entry/open price
            exit_price: Exit/close price
            size: Position size
            size_type: How size is expressed ('lots', 'units', 'contracts')
            trade_direction: 'buy' (long) or 'sell' (short)
            instrument_meta: Optional pre-fetched instrument metadata
            broker_profile: Optional broker-specific rules
            account_currency: Account base currency for P&L
            
        Returns:
            PnLResult with calculated values
        """
        if instrument_meta is None:
            instrument_meta = get_instrument_metadata(instrument_symbol)
        
        if instrument_meta is None:
            instrument_meta = {
                'type': 'unknown',
                'pip_or_tick_size': 0.0001,
                'tick_value': 10.0,
                'contract_size': 100000,
                'price_decimals': 5
            }
        
        inst_type = instrument_meta.get('type', 'unknown')
        
        if inst_type == 'forex':
            return PnLEngine._calculate_forex(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
        elif inst_type == 'index':
            return PnLEngine._calculate_index(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
        elif inst_type == 'commodity':
            return PnLEngine._calculate_commodity(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
        elif inst_type == 'crypto':
            return PnLEngine._calculate_crypto(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
        elif inst_type in ('stock', 'etf'):
            return PnLEngine._calculate_stock(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
        else:
            return PnLEngine._calculate_generic(
                entry_price, exit_price, size, size_type, trade_direction,
                instrument_meta, broker_profile, account_currency
            )
    
    @staticmethod
    def _calculate_forex(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Calculate P&L for forex pairs.
        
        Formula: pip_move * pip_value * lots
        pip_value = (pip_size / exit_price) * contract_size (for pairs where USD is base)
        """
        pip_size = meta.get('pip_or_tick_size', 0.0001)
        contract_size = meta.get('contract_size', 100000)
        tick_value = meta.get('tick_value', 10.0)
        
        if broker and 'lot_size_rule' in broker:
            lot_rules = broker['lot_size_rule']
            contract_size = lot_rules.get('forex', contract_size)
        
        if size_type == 'lots':
            units = size * contract_size
        elif size_type == 'units':
            units = size
        else:
            units = size * contract_size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        pip_move = price_diff / pip_size
        
        pip_value_per_unit = pip_size * tick_value / pip_size
        pnl = pip_move * (pip_value_per_unit * units / contract_size)
        
        pnl = price_diff * units
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=round(pip_move, 1),
            points=None,
            tick_move=round(pip_move, 1),
            details={
                'calculation_type': 'forex',
                'pip_size': pip_size,
                'contract_size': contract_size,
                'units': units,
                'price_diff': price_diff,
                'direction': direction
            }
        )
    
    @staticmethod
    def _calculate_index(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Calculate P&L for indices.
        
        Formula: points * tick_value * contracts
        """
        tick_size = meta.get('pip_or_tick_size', 1.0)
        tick_value = meta.get('tick_value', 1.0)
        contract_size = meta.get('contract_size', 1)
        
        if broker and 'lot_size_rule' in broker:
            lot_rules = broker['lot_size_rule']
            contract_size = lot_rules.get('indices', contract_size)
        
        if size_type == 'lots':
            contracts = size
        elif size_type == 'contracts':
            contracts = size
        else:
            contracts = size / contract_size if contract_size else size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        points = price_diff
        ticks = price_diff / tick_size if tick_size else 0
        
        pnl = points * tick_value * contracts
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=None,
            points=round(points, 2),
            tick_move=round(ticks, 1),
            details={
                'calculation_type': 'index',
                'tick_size': tick_size,
                'tick_value': tick_value,
                'contracts': contracts,
                'price_diff': price_diff,
                'direction': direction
            }
        )
    
    @staticmethod
    def _calculate_commodity(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Calculate P&L for commodities.
        
        Formula: price_diff * contract_size * contracts
        """
        tick_size = meta.get('pip_or_tick_size', 0.01)
        tick_value = meta.get('tick_value', 1.0)
        contract_size = meta.get('contract_size', 100)
        
        if broker and 'lot_size_rule' in broker:
            lot_rules = broker['lot_size_rule']
            contract_size = lot_rules.get('commodities', contract_size)
        
        if size_type == 'lots':
            contracts = size
        elif size_type == 'contracts':
            contracts = size
        else:
            contracts = size / contract_size if contract_size else size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        tick_move = price_diff / tick_size if tick_size else 0
        
        pnl = price_diff * contract_size * contracts
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=None,
            points=round(price_diff, 4),
            tick_move=round(tick_move, 1),
            details={
                'calculation_type': 'commodity',
                'tick_size': tick_size,
                'tick_value': tick_value,
                'contract_size': contract_size,
                'contracts': contracts,
                'price_diff': price_diff,
                'direction': direction
            }
        )
    
    @staticmethod
    def _calculate_crypto(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Calculate P&L for crypto.
        
        Formula: quantity * (exit_price - entry_price)
        """
        contract_size = meta.get('contract_size', 1)
        tick_size = meta.get('pip_or_tick_size', 0.01)
        
        if size_type == 'lots':
            quantity = size * contract_size
        elif size_type == 'contracts':
            quantity = size * contract_size
        else:
            quantity = size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        pnl = quantity * price_diff
        
        pct_move = (price_diff / entry_price * 100) if entry_price else 0
        tick_move = price_diff / tick_size if tick_size else 0
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=None,
            points=round(pct_move, 2),
            tick_move=round(tick_move, 1),
            details={
                'calculation_type': 'crypto',
                'quantity': quantity,
                'price_diff': price_diff,
                'pct_move': pct_move,
                'direction': direction
            }
        )
    
    @staticmethod
    def _calculate_stock(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Calculate P&L for stocks/ETFs.
        
        Formula: shares * (exit_price - entry_price)
        """
        if size_type in ('lots', 'contracts'):
            shares = size
        else:
            shares = size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        pnl = shares * price_diff
        pct_return = (price_diff / entry_price * 100) if entry_price else 0
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=None,
            points=round(price_diff, 2),
            tick_move=None,
            details={
                'calculation_type': 'stock',
                'shares': shares,
                'price_diff': price_diff,
                'pct_return': round(pct_return, 2),
                'direction': direction
            }
        )
    
    @staticmethod
    def _calculate_generic(
        entry_price: float,
        exit_price: float,
        size: float,
        size_type: str,
        direction: str,
        meta: Dict[str, Any],
        broker: Optional[Dict[str, Any]],
        account_currency: str
    ) -> PnLResult:
        """
        Generic P&L calculation for unknown instrument types.
        
        Uses: size * (exit - entry) * contract_size
        """
        contract_size = meta.get('contract_size', 1)
        tick_size = meta.get('pip_or_tick_size', 0.01)
        
        if size_type == 'lots':
            quantity = size * contract_size
        else:
            quantity = size
        
        price_diff = exit_price - entry_price
        if direction == 'sell':
            price_diff = -price_diff
        
        pnl = quantity * price_diff
        tick_move = price_diff / tick_size if tick_size else 0
        
        return PnLResult(
            pnl=round(pnl, 2),
            pnl_currency=account_currency,
            pip_move=None,
            points=round(price_diff, 4),
            tick_move=round(tick_move, 1),
            details={
                'calculation_type': 'generic',
                'quantity': quantity,
                'price_diff': price_diff,
                'direction': direction
            }
        )


def calculate_pnl(*args, **kwargs) -> Dict[str, Any]:
    """Flexible convenience wrapper for P&L calculation.

    Supports two calling signatures for backward compatibility:
    1) calculate_pnl(symbol, instrument_meta_dict, entry_price, exit_price, size, ...)
    2) calculate_pnl(symbol, entry_price, exit_price, size, size_type=..., instrument_meta=..., ...)

    Always returns a dict (result.to_dict()).
    """
    # Default values
    size_type = kwargs.pop('size_type', 'lots')
    trade_direction = kwargs.pop('trade_direction', 'buy')
    broker_profile = kwargs.pop('broker_profile', None)
    account_currency = kwargs.pop('account_currency', 'USD')

    # If caller used keyword args (common in tests), pull values from kwargs
    if 'instrument_symbol' in kwargs:
        instrument_symbol = kwargs.pop('instrument_symbol')
        entry_price = kwargs.pop('entry_price')
        exit_price = kwargs.pop('exit_price')
        size = kwargs.pop('size')
        instrument_meta = kwargs.pop('instrument_meta', None)
    else:
        # Detect signature: if second positional arg is a dict, treat it as instrument_meta
        if len(args) >= 2 and isinstance(args[1], dict):
            instrument_symbol = args[0]
            instrument_meta = args[1]
            entry_price = args[2]
            exit_price = args[3]
            size = args[4]
        else:
            # Legacy ordering: symbol, entry_price, exit_price, size
            instrument_symbol = args[0]
            entry_price = args[1]
            exit_price = args[2]
            size = args[3]
            instrument_meta = kwargs.pop('instrument_meta', None)

    result = PnLEngine.calculate(
        instrument_symbol=instrument_symbol,
        entry_price=entry_price,
        exit_price=exit_price,
        size=size,
        size_type=size_type,
        trade_direction=trade_direction,
        instrument_meta=instrument_meta,
        broker_profile=broker_profile,
        account_currency=account_currency
    )

    # Return serializable dict for tests and callers
    if isinstance(result, PnLResult):
        return result.to_dict()
    # If older code returns dict already
    return dict(result)


def calculate_pip_value(
    instrument_symbol: str,
    lot_size: float = 1.0,
    instrument_meta: Optional[Dict[str, Any]] = None,
    account_currency: str = 'USD'
) -> float:
    """Calculate pip value for a forex pair."""
    if instrument_meta is None:
        instrument_meta = get_instrument_metadata(instrument_symbol)
    
    if instrument_meta is None:
        return 10.0
    
    pip_size = instrument_meta.get('pip_or_tick_size', 0.0001)
    contract_size = instrument_meta.get('contract_size', 100000)
    
    pip_value = pip_size * contract_size * lot_size
    
    return round(pip_value, 2)


def calculate_position_size(
    instrument_symbol: str,
    risk_amount: float,
    stop_loss_pips: float,
    instrument_meta: Optional[Dict[str, Any]] = None,
    account_currency: str = 'USD'
) -> float:
    """
    Calculate position size based on risk parameters.
    
    Args:
        instrument_symbol: The instrument to trade
        risk_amount: Amount willing to risk in account currency
        stop_loss_pips: Stop loss distance in pips
        
    Returns:
        Lot size for the position
    """
    pip_value = calculate_pip_value(instrument_symbol, 1.0, instrument_meta, account_currency)
    
    if pip_value <= 0 or stop_loss_pips <= 0:
        return 0.01
    
    lot_size = risk_amount / (stop_loss_pips * pip_value)
    
    lot_size = max(0.01, round(lot_size, 2))
    
    return lot_size
