"""
Exness-Style P&L Calculator

Unified P&L calculation service that properly handles different instrument categories
with their correct contract sizes and calculation methods.

This calculator reads instrument metadata from the database and applies category-specific
formulas to match Exness behavior.

Categories supported:
- Forex: Standard lot calculation with contract size
- Crypto: Direct price movement * quantity
- Crypto Cross: Same as crypto
- Indices: Points * tick_value * lots
- IDX-Large: Amplified indices (10x, 100x contracts)
- Stocks: Shares * price difference
- Energies: Oil/Gas with contract multipliers
- Forex Indicator: Currency basket indices
"""

from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PnLResult:
    """Result of P&L calculation"""
    pnl: float
    pips_or_points: float
    calculation_method: str
    details: Dict[str, Any]


class ExnessPnLCalculator:
    """
    Unified P&L calculator for Exness-style instruments.
    
    Uses instrument metadata from database to calculate accurate P&L
    based on the specific instrument category and its contract specifications.
    """
    
    # Default values if instrument not found in database
    DEFAULT_CONTRACT_SIZES = {
        'forex': 100000,           # Standard forex lot
        'crypto': 1,                # Crypto: 1 unit per lot
        'index': 1,                # Index: 1 contract
        'stock': 1,                # Stock: 1 share
        'commodity': 100,          # Default commodity
        'forex_indicator': 1000,    # Forex indicators
    }
    
    DEFAULT_PIP_SIZES = {
        'forex': 0.0001,           # Standard forex pip
        'crypto': 0.01,            # Crypto tick
        'index': 1.0,              # Index point
        'stock': 0.01,             # Stock cent
        'commodity': 0.01,         # Commodity tick
        'forex_indicator': 0.001,  # Forex indicator
    }
    
    @staticmethod
    def get_instrument_metadata(symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get instrument metadata from database.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with instrument metadata or None if not found
        """
        try:
            from app.models.instrument import Instrument
            
            # Try exact match first
            instrument = Instrument.query.filter(
                Instrument.symbol.ilike(symbol)
            ).first()
            
            if instrument:
                return {
                    'symbol': instrument.symbol,
                    'instrument_type': instrument.instrument_type,
                    'category': instrument.category,
                    'pip_size': instrument.pip_size,
                    'tick_value': instrument.tick_value,
                    'contract_size': instrument.contract_size,
                    'price_decimals': instrument.price_decimals,
                    'pnl_method': instrument.pnl_method,
                }
        except Exception as e:
            logger.warning(f"Could not fetch instrument metadata: {e}")
        
        return None
    
    @staticmethod
    def get_fallback_metadata(symbol: str) -> Dict[str, Any]:
        """
        Get fallback metadata based on symbol patterns when DB lookup fails.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with inferred metadata
        """
        symbol_upper = symbol.upper()
        
        # Detect category from symbol patterns
        if symbol_upper.endswith('X10') or symbol_upper.endswith('X100'):
            # IDX-Large amplified indices
            return {
                'instrument_type': 'index',
                'category': 'IDX-Large',
                'pip_size': 1.0 if 'US30' in symbol_upper else 0.1,
                'tick_value': 10.0 if 'US30' in symbol_upper else 100.0,
                'contract_size': 10 if 'X10' in symbol_upper else 100,
            }
        
        # Crypto Cross (non-USD base)
        crypto_bases = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'DOGE']
        non_usd_quotes = ['JPY', 'AUD', 'EUR', 'GBP', 'CNH', 'THB', 'ZAR', 'XAU']
        for base in crypto_bases:
            for quote in non_usd_quotes:
                if symbol_upper.startswith(base) and symbol_upper.endswith(quote):
                    return {
                        'instrument_type': 'crypto',
                        'category': 'Crypto Cross',
                        'pip_size': 0.01 if quote == 'JPY' else 0.0001,
                        'tick_value': 1.0,
                        'contract_size': 1,
                    }
        
        # Regular Crypto
        if any(symbol_upper.startswith(c) for c in ['BTC', 'ETH', 'LTC', 'XRP', 'SOL', 'DOGE']):
            if 'USD' in symbol_upper:
                return {
                    'instrument_type': 'crypto',
                    'category': 'Crypto',
                    'pip_size': 0.01,
                    'tick_value': 1.0,
                    'contract_size': 1,
                }
        
        # Indices
        index_symbols = ['US30', 'US500', 'US100', 'NAS100', 'USTEC', 'GER40', 'UK100', 
                        'FRA40', 'JPN225', 'HK50', 'AUS200', 'EU50']
        if any(idx in symbol_upper for idx in index_symbols):
            tick_value = 5.0 if 'US30' in symbol_upper else 20.0 if 'US100' in symbol_upper else 1.0
            return {
                'instrument_type': 'index',
                'category': 'Indices',
                'pip_size': 1.0 if 'US30' in symbol_upper else 0.25,
                'tick_value': tick_value,
                'contract_size': 1,
            }
        
        # Energies
        if symbol_upper in ['USOIL', 'UKOIL', 'XNGUSD', 'NATGAS']:
            return {
                'instrument_type': 'commodity',
                'category': 'Energies',
                'pip_size': 0.01,
                'tick_value': 10.0,
                'contract_size': 1000 if 'OIL' in symbol_upper else 10000,
            }
        
        # Metals (XAU, XAG)
        if symbol_upper.startswith('XAU'):
            return {
                'instrument_type': 'commodity',
                'category': 'Energies',  # Grouped with energies in some systems
                'pip_size': 0.01,
                'tick_value': 1.0,
                'contract_size': 100,
            }
        if symbol_upper.startswith('XAG'):
            return {
                'instrument_type': 'commodity',
                'category': 'Energies',
                'pip_size': 0.001,
                'tick_value': 5.0,
                'contract_size': 5000,
            }
        
        # Stocks (1-5 letter uppercase symbols)
        if len(symbol_upper) <= 5 and symbol_upper.isalpha():
            return {
                'instrument_type': 'stock',
                'category': 'Stocks',
                'pip_size': 0.01,
                'tick_value': 1.0,
                'contract_size': 1,
            }
        
        # Forex Indicator
        if symbol_upper.endswith('X') and len(symbol_upper) == 4:
            return {
                'instrument_type': 'forex_indicator',
                'category': 'Forex Indicator',
                'pip_size': 0.001,
                'tick_value': 1.0,
                'contract_size': 1000,
            }
        
        # Default to forex
        pip_size = 0.01 if symbol_upper.endswith('JPY') else 0.0001
        return {
            'instrument_type': 'forex',
            'category': 'Forex',
            'pip_size': pip_size,
            'tick_value': 1000.0 if symbol_upper.endswith('JPY') else 10.0,
            'contract_size': 100000,
        }
    
    @classmethod
    def calculate_pnl(
        cls,
        symbol: str,
        trade_type: str,
        entry_price: float,
        exit_price: float,
        lot_size: float,
        commission: float = 0.0,
        swap: float = 0.0
    ) -> Tuple[float, float, str]:
        """
        Calculate P&L for a trade.
        
        Args:
            symbol: Trading symbol
            trade_type: 'BUY' or 'SELL'
            entry_price: Entry price
            exit_price: Exit price
            lot_size: Position size in lots
            commission: Commission cost
            swap: Overnight swap
            
        Returns:
            Tuple of (pnl, pips_or_points, calculation_method)
        """
        # Get metadata from database first
        metadata = cls.get_instrument_metadata(symbol)
        
        if metadata is None:
            # Fall back to pattern-based detection
            metadata = cls.get_fallback_metadata(symbol)
        
        # Determine direction
        is_buy = trade_type.upper() == 'BUY'
        
        # Calculate price difference based on direction
        if is_buy:
            price_diff = exit_price - entry_price
        else:
            price_diff = entry_price - exit_price
        
        # Get instrument type and category
        instrument_type = metadata.get('instrument_type', 'forex')
        category = metadata.get('category', 'Forex')
        
        # Calculate P&L based on category
        if instrument_type == 'forex' or category == 'Forex':
            pnl, pips = cls._calculate_forex(
                price_diff, lot_size, metadata, is_buy, entry_price, exit_price
            )
            method = 'forex'
            
        elif instrument_type == 'crypto' or 'Crypto' in category:
            pnl, pips = cls._calculate_crypto(
                price_diff, lot_size, metadata, is_buy
            )
            method = 'crypto'
            
        elif instrument_type == 'index':
            if 'IDX-Large' in category:
                pnl, pips = cls._calculate_idx_large(
                    price_diff, lot_size, metadata, is_buy
                )
                method = 'idx_large'
            else:
                pnl, pips = cls._calculate_index(
                    price_diff, lot_size, metadata, is_buy
                )
                method = 'index'
                
        elif instrument_type == 'stock' or category == 'Stocks':
            pnl, pips = cls._calculate_stock(
                price_diff, lot_size, metadata, is_buy
            )
            method = 'stock'
            
        elif instrument_type == 'commodity' or category in ['Energies', 'Commodity']:
            pnl, pips = cls._calculate_commodity(
                price_diff, lot_size, metadata, is_buy
            )
            method = 'commodity'
            
        elif instrument_type == 'forex_indicator' or category == 'Forex Indicator':
            pnl, pips = cls._calculate_forex_indicator(
                price_diff, lot_size, metadata, is_buy
            )
            method = 'forex_indicator'
            
        else:
            # Generic calculation
            pnl, pips = cls._calculate_generic(
                price_diff, lot_size, metadata, is_buy
            )
            method = 'generic'
        
        # Apply commission and swap
        final_pnl = pnl - commission + swap
        
        return round(final_pnl, 2), round(pips, 1), method
    
    @staticmethod
    def _calculate_forex(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool,
        entry_price: float,
        exit_price: float
    ) -> Tuple[float, float]:
        """
        Calculate Forex P&L.
        
        Formula: price_diff * contract_size * lot_size
        
        For standard forex:
        - 1 lot = 100,000 units
        - P&L = price_diff * 100,000 * lots
        """
        contract_size = metadata.get('contract_size', 100000)
        pip_size = metadata.get('pip_size', 0.0001)
        
        # P&L = price difference * contract size * lot size
        pnl = price_diff * contract_size * lot_size
        
        # Calculate pips (price difference / pip size)
        pips = price_diff / pip_size if pip_size > 0 else 0
        
        return pnl, pips
    
    @staticmethod
    def _calculate_crypto(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate Crypto P&L.
        
        Formula: price_diff * contract_size * lot_size
        
        For crypto (Exness-style):
        - 1 lot = 1 unit of the base currency
        - P&L = price difference * lots
        """
        contract_size = metadata.get('contract_size', 1)
        
        # Crypto: direct price movement * quantity
        pnl = price_diff * contract_size * lot_size
        
        # Pips for crypto is just the price difference
        pips = price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_index(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate Index P&L.
        
        Formula: price_diff * tick_value * lots
        
        For indices:
        - tick_value represents $ per point movement
        - US30: ~$5 per point
        - US100 (Nasdaq): ~$20 per point
        - US500: ~$50 per point (0.25 * 200)
        """
        tick_value = metadata.get('tick_value', 1.0)
        
        # Index P&L = price difference * tick value * lots
        pnl = price_diff * tick_value * lot_size
        
        # Points = price difference
        pips = price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_idx_large(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate IDX-Large (amplified index) P&L.
        
        These are 10x or 100x leveraged index contracts:
        - US30_x10: 10x multiplier
        - USTEC_x100: 100x multiplier
        - US500_x100: 100x multiplier
        """
        tick_value = metadata.get('tick_value', 1.0)
        contract_size = metadata.get('contract_size', 1)
        
        # IDX-Large: amplified tick value * lots
        pnl = price_diff * tick_value * contract_size * lot_size
        
        pips = price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_stock(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate Stock P&L.
        
        Formula: price_diff * shares
        
        For stocks:
        - 1 lot = 1 share (typically)
        - P&L = price difference * shares
        """
        contract_size = metadata.get('contract_size', 1)
        
        # Stock P&L = price difference * shares
        pnl = price_diff * contract_size * lot_size
        
        # Points = price difference
        pips = price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_commodity(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate Commodity/Energy P&L.
        
        Formula: price_diff * contract_size * lots
        
        For energies:
        - USOIL/UKOIL: 1000 barrels per lot, ~$10 per point
        - Natural Gas: 10000 mmBtu per lot
        """
        contract_size = metadata.get('contract_size', 100)
        
        # Commodity P&L = price difference * contract size * lots
        pnl = price_diff * contract_size * lot_size
        
        # Calculate points/ticks
        pip_size = metadata.get('pip_size', 0.01)
        pips = price_diff / pip_size if pip_size > 0 else price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_forex_indicator(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Calculate Forex Indicator P&L.
        
        Formula: price_diff * contract_size * lots
        
        Forex indicators (USDX, EURX, etc.):
        - Track currency basket strength
        - Standard contract size: 1000
        """
        contract_size = metadata.get('contract_size', 1000)
        
        pnl = price_diff * contract_size * lot_size
        
        pips = price_diff
        
        return pnl, pips
    
    @staticmethod
    def _calculate_generic(
        price_diff: float,
        lot_size: float,
        metadata: Dict[str, Any],
        is_buy: bool
    ) -> Tuple[float, float]:
        """
        Generic P&L calculation for unknown instrument types.
        
        Fallback method.
        """
        contract_size = metadata.get('contract_size', 1)
        
        pnl = price_diff * contract_size * lot_size
        pips = price_diff
        
        return pnl, pips


# Convenience function for easy importing
def calculate_pnl(
    symbol: str,
    trade_type: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    commission: float = 0.0,
    swap: float = 0.0
) -> Tuple[float, float, str]:
    """
    Calculate P&L for a trade using Exness-style methodology.
    
    Args:
        symbol: Trading symbol
        trade_type: 'BUY' or 'SELL'
        entry_price: Entry price
        exit_price: Exit price
        lot_size: Position size in lots
        commission: Commission cost (default 0)
        swap: Overnight swap (default 0)
    
    Returns:
        Tuple of (pnl, pips_or_points, calculation_method)
    """
    return ExnessPnLCalculator.calculate_pnl(
        symbol=symbol,
        trade_type=trade_type,
        entry_price=entry_price,
        exit_price=exit_price,
        lot_size=lot_size,
        commission=commission,
        swap=swap
    )


# Backward compatibility - map to old function signature
def calculate_pnl_detailed(
    symbol: str,
    trade_type: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    commission: float = 0.0,
    swap: float = 0.0
) -> dict:
    """
    Calculate P&L with detailed breakdown.
    
    Returns dictionary with full calculation details.
    """
    pnl, pips, method = calculate_pnl(
        symbol, trade_type, entry_price, exit_price,
        lot_size, commission, swap
    )
    
    return {
        'symbol': symbol,
        'trade_type': trade_type,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'lot_size': lot_size,
        'profit_loss': pnl,
        'pips': pips,
        'calculation_method': method,
        'commission': commission,
        'swap': swap,
    }


# Test function
if __name__ == '__main__':
    print("=" * 60)
    print("Exness P&L Calculator Test")
    print("=" * 60)
    
    test_cases = [
        # Forex pairs
        {'symbol': 'EURUSD', 'type': 'BUY', 'entry': 1.1000, 'exit': 1.1050, 'lots': 1.0, 'expected': '$500 (50 pips * $10/pip)'},
        {'symbol': 'EURUSD', 'type': 'SELL', 'entry': 1.1000, 'exit': 1.1050, 'lots': 1.0, 'expected': '-$500'},
        {'symbol': 'USDJPY', 'type': 'BUY', 'entry': 150.00, 'exit': 150.50, 'lots': 1.0, 'expected': '~$500 (50 pips * 1000 JPY/lot)'},
        {'symbol': 'USDCAD', 'type': 'BUY', 'entry': 1.3500, 'exit': 1.3550, 'lots': 1.0, 'expected': '$500'},
        
        # Crypto
        {'symbol': 'BTCUSD', 'type': 'BUY', 'entry': 50000, 'exit': 51000, 'lots': 1.0, 'expected': '$1000'},
        {'symbol': 'BTCUSD', 'type': 'BUY', 'entry': 50000, 'exit': 50100, 'lots': 0.1, 'expected': '$10'},
        
        # Indices
        {'symbol': 'US30', 'type': 'BUY', 'entry': 35000, 'exit': 35100, 'lots': 1.0, 'expected': '$500 (100 points * $5/point)'},
        {'symbol': 'US100', 'type': 'BUY', 'entry': 15000, 'exit': 15100, 'lots': 1.0, 'expected': '$2000 (100 points * $20/point)'},
        
        # IDX-Large (amplified)
        {'symbol': 'US30_x10', 'type': 'BUY', 'entry': 35000, 'exit': 35100, 'lots': 1.0, 'expected': '$5000 (100 points * $50/point)'},
        
        # Stocks
        {'symbol': 'AAPL', 'type': 'BUY', 'entry': 150, 'exit': 160, 'lots': 10.0, 'expected': '$100'},
        
        # Energies
        {'symbol': 'USOIL', 'type': 'BUY', 'entry': 80.00, 'exit': 81.00, 'lots': 1.0, 'expected': '$1000 (100 points * $10/point * 1 lot)'},
    ]
    
    for tc in test_cases:
        pnl, pips, method = calculate_pnl(
            tc['symbol'], tc['type'], tc['entry'], tc['exit'], tc['lots']
        )
        
        print(f"\n{tc['symbol']} {tc['type']} {tc['lots']} lot(s)")
        print(f"  Entry: {tc['entry']} -> Exit: {tc['exit']}")
        print(f"  P&L: ${pnl:.2f} | Pips/Points: {pips:.1f} | Method: {method}")
        print(f"  Expected: {tc['expected']}")
    
    print("\n" + "=" * 60)

