"""
Advanced P&L Calculator
Handles dynamic P&L calculations for different instrument types:
- Forex (pips)
- Indices (points × tick value)
- Crypto (quantity × price movement)
- Stocks (quantity × price movement)
- Commodities (contract multipliers)
"""

from enum import Enum
from typing import Dict, Tuple, Optional

class InstrumentType(Enum):
    FOREX = "forex"
    INDEX = "index"
    CRYPTO = "crypto"
    STOCK = "stock"
    COMMODITY = "commodity"

def detect_instrument_type(symbol: str) -> InstrumentType:
    """Detect instrument type from symbol"""
    symbol = symbol.upper()
    
    # Forex detection: currency pairs (4 chars, all letters)
    if len(symbol) == 6 and symbol.isalpha():
        return InstrumentType.FOREX
    
    # Crypto detection: ends with USD, contains common crypto names
    if symbol.endswith('USD') and any(c in symbol for c in ['BTC', 'ETH', 'XRP', 'BNB', 'XAU', 'XAG']):
        return InstrumentType.CRYPTO
    
    # Commodity detection: XAU (gold), XAG (silver), WTI, etc.
    if any(c in symbol for c in ['XAU', 'XAG', 'WTI', 'CL', 'NG']):
        return InstrumentType.COMMODITY
    
    # Index detection: common index symbols
    if symbol in ['SPX', 'NDX', 'DXY', 'VIX', 'FTSE', 'DAX', 'N225']:
        return InstrumentType.INDEX
    
    # Stock detection: 1-5 letter symbols
    if 1 <= len(symbol) <= 5:
        return InstrumentType.STOCK
    
    # Default to stock
    return InstrumentType.STOCK


class PnLCalculator:
    """
    Dynamic P&L calculator supporting all instrument types.
    
    Usage:
        calc = PnLCalculator(instrument_type, pip_size, tick_value, contract_size)
        pnl = calc.calculate_pnl(entry, exit, qty, trade_type)
        pips = calc.calculate_pips(entry, exit, trade_type)
        exit_price = calc.reverse_calculate_exit(entry, qty, target_pnl, trade_type)
    """
    
    def __init__(self, instrument_type: InstrumentType, pip_size: float = 0.0001, 
                 tick_value: float = 1.0, contract_size: float = 1.0):
        """Initialize calculator with instrument metadata"""
        self.instrument_type = instrument_type
        self.pip_size = pip_size
        self.tick_value = tick_value
        self.contract_size = contract_size
    
    def calculate_pnl(self, entry_price: float, exit_price: float, quantity: float, 
                      trade_type: str = 'BUY') -> Tuple[float, float]:
        """
        Calculate P&L based on instrument type.
        
        Returns: (profit_loss, profit_loss_pips or points)
        """
        if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
            return 0.0, 0.0
        
        # Determine price movement (positive = profit for BUY, loss for SELL)
        if trade_type.upper() == 'BUY':
            price_diff = exit_price - entry_price
        else:  # SELL
            price_diff = entry_price - exit_price
        
        if self.instrument_type == InstrumentType.FOREX:
            return self._calculate_forex_pnl(entry_price, exit_price, quantity, trade_type, price_diff)
        elif self.instrument_type == InstrumentType.INDEX:
            return self._calculate_index_pnl(price_diff, quantity)
        elif self.instrument_type == InstrumentType.CRYPTO:
            return self._calculate_crypto_pnl(price_diff, quantity)
        elif self.instrument_type == InstrumentType.STOCK:
            return self._calculate_stock_pnl(price_diff, quantity)
        elif self.instrument_type == InstrumentType.COMMODITY:
            return self._calculate_commodity_pnl(price_diff, quantity)
        else:
            # Fallback to stock calculation
            return self._calculate_stock_pnl(price_diff, quantity)
    
    def _calculate_forex_pnl(self, entry: float, exit: float, qty: float, trade_type: str, 
                             price_diff: float) -> Tuple[float, float]:
        """Forex: profit = pips × pip_size × contract_size × quantity"""
        # Calculate pips
        pips = price_diff / self.pip_size
        
        # Calculate P&L: pips × pip value
        # Standard: 1 pip on 1 lot = $10 (for most pairs, varies by pair)
        pip_value = self.pip_size * self.contract_size * 10  # Approximate
        pnl = pips * pip_value * (qty / 1.0)
        
        return round(pnl, 2), round(pips, 2)
    
    def _calculate_index_pnl(self, price_diff: float, quantity: float) -> Tuple[float, float]:
        """Index: profit = price_diff × tick_value × quantity"""
        points = price_diff  # Each point is worth tick_value
        pnl = points * self.tick_value * quantity
        return round(pnl, 2), round(points, 2)
    
    def _calculate_crypto_pnl(self, price_diff: float, quantity: float) -> Tuple[float, float]:
        """Crypto: profit = price_diff × quantity (linear)"""
        pnl = price_diff * quantity
        return round(pnl, 2), round(pnl / quantity if quantity > 0 else 0, 2)
    
    def _calculate_stock_pnl(self, price_diff: float, quantity: float) -> Tuple[float, float]:
        """Stock: profit = price_diff × quantity"""
        pnl = price_diff * quantity
        return round(pnl, 2), round(pnl / quantity if quantity > 0 else 0, 2)
    
    def _calculate_commodity_pnl(self, price_diff: float, quantity: float) -> Tuple[float, float]:
        """Commodity: profit = price_diff × contract_size × quantity"""
        pnl = price_diff * self.contract_size * quantity
        return round(pnl, 2), round(pnl / (self.contract_size * quantity) if quantity > 0 else 0, 2)
    
    def calculate_pips(self, entry_price: float, exit_price: float, trade_type: str = 'BUY') -> float:
        """Calculate pips (or points) for a price movement"""
        if entry_price <= 0:
            return 0.0
        
        if trade_type.upper() == 'BUY':
            price_diff = exit_price - entry_price
        else:
            price_diff = entry_price - exit_price
        
        if self.instrument_type == InstrumentType.FOREX:
            pips = price_diff / self.pip_size
        else:
            # For others, return points or simple difference
            pips = price_diff
        
        return round(pips, 2)
    
    def reverse_calculate_exit(self, entry_price: float, quantity: float, target_pnl: float, 
                               trade_type: str = 'BUY') -> float:
        """
        Reverse-calculate exit price from target P&L.
        Useful when user enters P&L first and wants to know exit price.
        """
        if entry_price <= 0 or quantity <= 0:
            return 0.0
        
        try:
            if self.instrument_type == InstrumentType.FOREX:
                # pnl = pips × pip_value × qty
                # pips = pnl / (pip_value × qty)
                pip_value = self.pip_size * self.contract_size * 10
                pips = target_pnl / (pip_value * quantity)
                price_diff = pips * self.pip_size
            
            elif self.instrument_type == InstrumentType.INDEX:
                # pnl = points × tick_value × qty
                points = target_pnl / (self.tick_value * quantity)
                price_diff = points
            
            elif self.instrument_type in [InstrumentType.CRYPTO, InstrumentType.STOCK]:
                # pnl = price_diff × qty
                price_diff = target_pnl / quantity
            
            elif self.instrument_type == InstrumentType.COMMODITY:
                # pnl = price_diff × contract_size × qty
                price_diff = target_pnl / (self.contract_size * quantity)
            
            else:
                price_diff = target_pnl / quantity
            
            # Calculate exit from price_diff
            if trade_type.upper() == 'BUY':
                exit_price = entry_price + price_diff
            else:
                exit_price = entry_price - price_diff
            
            return round(exit_price, 4)
        
        except (ZeroDivisionError, ValueError):
            return 0.0


# Factory function for easier use
def create_calculator(instrument_type: str, pip_size: float = 0.0001, 
                     tick_value: float = 1.0, contract_size: float = 1.0) -> PnLCalculator:
    """Create a P&L calculator for the given instrument type"""
    if isinstance(instrument_type, str):
        try:
            instrument_type = InstrumentType(instrument_type.lower())
        except ValueError:
            instrument_type = InstrumentType.STOCK
    
    return PnLCalculator(instrument_type, pip_size, tick_value, contract_size)
