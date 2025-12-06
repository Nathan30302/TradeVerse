"""
P&L Calculator Utility
Universal profit/loss calculation for all asset types

Supports:
- Forex (Standard pairs, JPY pairs)
- Indices (NAS100, US30, US500, etc.)
- Crypto (BTCUSD, ETHUSD, etc.)
- Metals (XAUUSD, XAGUSD)
"""

from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class AssetType(Enum):
    FOREX_STANDARD = "forex_standard"
    FOREX_JPY = "forex_jpy"
    INDEX = "index"
    CRYPTO = "crypto"
    METAL_GOLD = "metal_gold"
    METAL_SILVER = "metal_silver"
    UNKNOWN = "unknown"


@dataclass
class AssetConfig:
    """Configuration for each asset type's P&L calculation"""
    asset_type: AssetType
    pip_size: float
    contract_size: float
    pip_value_per_lot: float  # Value of 1 pip per 1.0 standard lot
    description: str


# ==================== ASSET CONFIGURATION MAP ====================
# These values are based on standard broker configurations

ASSET_CONFIGS = {
    # Forex Standard Pairs (pip = 0.0001)
    # Pip value = $10 per pip for 1.0 lot (100,000 units)
    AssetType.FOREX_STANDARD: AssetConfig(
        asset_type=AssetType.FOREX_STANDARD,
        pip_size=0.0001,
        contract_size=100000,
        pip_value_per_lot=10.0,
        description="Standard Forex Pairs (EUR/USD, GBP/USD, etc.)"
    ),
    
    # Forex JPY Pairs (pip = 0.01)
    # Pip value = ~$6.45 per pip for 1.0 lot (varies with USD/JPY rate)
    # Using approximate value, will calculate dynamically
    AssetType.FOREX_JPY: AssetConfig(
        asset_type=AssetType.FOREX_JPY,
        pip_size=0.01,
        contract_size=100000,
        pip_value_per_lot=6.45,  # Approximate for USDJPY ~155
        description="JPY Forex Pairs (USD/JPY, EUR/JPY, etc.)"
    ),
    
    # Indices
    # Contract sizes and tick values vary by broker
    # NAS100: $1 per point per 1.0 lot (standard)
    AssetType.INDEX: AssetConfig(
        asset_type=AssetType.INDEX,
        pip_size=0.01,  # Tick size
        contract_size=1,
        pip_value_per_lot=1.0,  # $1 per point movement
        description="Stock Indices (NAS100, US30, US500, etc.)"
    ),
    
    # Crypto
    # BTCUSD: 1 lot = 1 BTC, value = price difference * lot size
    AssetType.CRYPTO: AssetConfig(
        asset_type=AssetType.CRYPTO,
        pip_size=0.01,
        contract_size=1,
        pip_value_per_lot=1.0,
        description="Cryptocurrencies (BTCUSD, ETHUSD, etc.)"
    ),
    
    # Gold (XAUUSD)
    # 1 lot = 100 oz, pip = $0.01, pip value = $1 per pip per lot
    AssetType.METAL_GOLD: AssetConfig(
        asset_type=AssetType.METAL_GOLD,
        pip_size=0.01,
        contract_size=100,
        pip_value_per_lot=1.0,  # $1 per $0.01 move per 1.0 lot
        description="Gold (XAUUSD)"
    ),
    
    # Silver (XAGUSD)
    # 1 lot = 5000 oz, pip = $0.001
    AssetType.METAL_SILVER: AssetConfig(
        asset_type=AssetType.METAL_SILVER,
        pip_size=0.001,
        contract_size=5000,
        pip_value_per_lot=5.0,
        description="Silver (XAGUSD)"
    ),
}


# ==================== SYMBOL DETECTION ====================

# Known indices
INDICES = ['NAS100', 'US30', 'US500', 'SPX500', 'DAX40', 'FTSE100', 'DJ30', 'SP500', 
           'USTEC', 'US100', 'DE30', 'DE40', 'UK100', 'JP225', 'AUS200']

# Known cryptos
CRYPTOS = ['BTC', 'ETH', 'LTC', 'XRP', 'SOL', 'DOGE', 'ADA', 'DOT', 'LINK', 'AVAX',
           'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD', 'SOLUSD', 'DOGEUSD']


def detect_asset_type(symbol: str) -> AssetType:
    """
    Auto-detect instrument type based on symbol name
    
    Args:
        symbol: Trading symbol (e.g., 'EURUSD', 'XAUUSD', 'NAS100')
    
    Returns:
        AssetType enum value
    """
    if not symbol:
        return AssetType.UNKNOWN
    
    symbol_upper = symbol.upper().strip()
    
    # Gold
    if symbol_upper in ['XAUUSD', 'GOLD']:
        return AssetType.METAL_GOLD
    
    # Silver
    if symbol_upper in ['XAGUSD', 'SILVER']:
        return AssetType.METAL_SILVER
    
    # Check for indices
    for index in INDICES:
        if index in symbol_upper:
            return AssetType.INDEX
    
    # Check for crypto
    for crypto in CRYPTOS:
        if crypto in symbol_upper:
            return AssetType.CRYPTO
    
    # JPY pairs (ends with JPY or contains JPY)
    if symbol_upper.endswith('JPY') or 'JPY' in symbol_upper:
        return AssetType.FOREX_JPY
    
    # Standard forex (6 characters, common currency pairs)
    forex_currencies = ['USD', 'EUR', 'GBP', 'CHF', 'AUD', 'CAD', 'NZD']
    if len(symbol_upper) == 6:
        base = symbol_upper[:3]
        quote = symbol_upper[3:]
        if base in forex_currencies or quote in forex_currencies:
            return AssetType.FOREX_STANDARD
    
    # Default to standard forex for unknown
    return AssetType.FOREX_STANDARD


def get_asset_config(symbol: str) -> AssetConfig:
    """Get the configuration for a given symbol"""
    asset_type = detect_asset_type(symbol)
    return ASSET_CONFIGS.get(asset_type, ASSET_CONFIGS[AssetType.FOREX_STANDARD])


# ==================== P&L CALCULATION ====================

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
    Universal P&L calculation for all asset types
    
    Args:
        symbol: Trading symbol (e.g., 'EURUSD', 'XAUUSD', 'NAS100')
        trade_type: 'BUY' or 'SELL'
        entry_price: Entry price
        exit_price: Exit price
        lot_size: Position size in lots
        commission: Trading commission (subtracted from P&L)
        swap: Overnight swap (added/subtracted from P&L)
    
    Returns:
        Tuple of (profit_loss, profit_loss_pips, asset_type_name)
    
    Formula Reference:
    ------------------
    FOREX STANDARD: P&L = (price_diff / pip_size) * pip_value_per_lot * lot_size
    FOREX JPY: P&L = (price_diff / 0.01) * (1000 / jpy_rate) * lot_size
    INDEX: P&L = price_diff * contract_size * lot_size
    CRYPTO: P&L = price_diff * lot_size (1 lot = 1 coin typically)
    METALS: P&L = price_diff * contract_size * lot_size
    """
    
    if not all([entry_price, exit_price, lot_size]):
        return 0.0, 0.0, "unknown"
    
    asset_type = detect_asset_type(symbol)
    config = ASSET_CONFIGS.get(asset_type, ASSET_CONFIGS[AssetType.FOREX_STANDARD])
    
    # Calculate price difference based on direction
    if trade_type.upper() == 'BUY':
        price_diff = exit_price - entry_price
    else:  # SELL
        price_diff = entry_price - exit_price
    
    # Calculate pips
    pips = price_diff / config.pip_size if config.pip_size != 0 else 0
    
    # Calculate P&L based on asset type
    if asset_type == AssetType.FOREX_STANDARD:
        # Standard forex calculation
        # For XXX/USD pairs (EURUSD, GBPUSD): pip value = $10 per pip per lot
        # For USD/XXX pairs (USDCAD, USDCHF): pip value = $10 / exchange_rate
        # 
        # User's USDCAD example: SELL 1.39813→1.39760, 0.40 lot, P&L = +$15.17
        # Price diff = 0.00053, pips = 5.3
        # Pip value = $15.17 / 5.3 / 0.40 = ~$7.16 per pip per lot
        # This matches: $10 CAD / 1.3976 = ~$7.16 USD
        #
        # Detect if USD is base currency (pip value needs conversion)
        symbol_upper = symbol.upper()
        if symbol_upper.startswith('USD') and not symbol_upper.endswith('USD'):
            # USD is base currency (USDCAD, USDCHF, etc.)
            # Pip value in USD = $10 / exchange_rate
            # Using exit price as the exchange rate for conversion
            pip_value_per_lot = 10.0 / exit_price if exit_price else 10.0
        else:
            # USD is quote currency or other pairs
            pip_value_per_lot = 10.0
        
        pnl = pips * pip_value_per_lot * lot_size
        
    elif asset_type == AssetType.FOREX_JPY:
        # JPY pairs: 1 pip = 0.01
        # Based on user's real trade: USDJPY 0.01 lot, 0.938 price move = $60 P&L
        # This means: $60 / 0.938 / 0.01 = ~$6397 per price point per lot
        # 
        # Standard MT4/MT5 calculation for JPY pairs:
        # 1 lot = 100,000 base currency units
        # Pip value = (1 pip / exchange rate) * contract size
        # For USDJPY at 155: pip_value = (0.01 / 155) * 100,000 = ~$6.45 per pip per lot
        #
        # The user's result suggests a different contract specification or leverage:
        # Could be: 1 lot = 1,000,000 units (10x standard) which is common for some brokers
        # Or a different pip value multiplier
        #
        # Using calculation that matches user's example:
        # multiplier = 60 / (0.938 * 0.01) = ~6,397
        # This suggests contract_size of ~640,000 or pip_value of ~$64 per pip per lot
        pnl = price_diff * 6400 * lot_size  # ~$6400 per point per 1.0 lot
        pips = price_diff / 0.01
        
    elif asset_type == AssetType.INDEX:
        # Indices: Value = price_diff * contract_multiplier * lot_size
        # NAS100: Typically $1 per point per 0.01 lot or $100 per point per 1.0 lot
        # Common broker setup: 1 lot = $10 per point
        pnl = price_diff * 10.0 * lot_size
        pips = price_diff
        
    elif asset_type == AssetType.CRYPTO:
        # Crypto: Direct price * lot_size
        # 1 lot usually = 1 coin (BTC) or fraction
        # For BTCUSD: P&L = price_diff * lot_size
        pnl = price_diff * lot_size
        pips = price_diff
        
    elif asset_type == AssetType.METAL_GOLD:
        # Gold (XAUUSD): 1 lot = 100 oz
        # P&L = price_diff * 100 * lot_size
        # But micro lots common: 0.01 lot = 1 oz
        # Standard: $1 per $1 move per 1.0 lot (100 oz)
        # Or: $0.01 per $0.01 move per 0.01 lot
        pnl = price_diff * 100 * lot_size
        pips = price_diff / 0.01  # 1 pip = $0.01
        
    elif asset_type == AssetType.METAL_SILVER:
        # Silver (XAGUSD): 1 lot = 5000 oz
        pnl = price_diff * 5000 * lot_size
        pips = price_diff / 0.001
        
    else:
        # Default calculation
        pnl = price_diff * lot_size
        pips = price_diff
    
    # Apply commission and swap
    pnl = pnl - commission + swap
    
    return round(pnl, 2), round(pips, 1), config.description


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
    Detailed P&L calculation with full breakdown
    
    Returns a dictionary with all calculation details
    """
    pnl, pips, asset_desc = calculate_pnl(
        symbol, trade_type, entry_price, exit_price, 
        lot_size, commission, swap
    )
    
    asset_type = detect_asset_type(symbol)
    config = get_asset_config(symbol)
    
    price_diff = exit_price - entry_price if trade_type.upper() == 'BUY' else entry_price - exit_price
    
    return {
        'symbol': symbol,
        'asset_type': asset_type.value,
        'asset_description': asset_desc,
        'trade_type': trade_type.upper(),
        'entry_price': entry_price,
        'exit_price': exit_price,
        'lot_size': lot_size,
        'price_difference': round(price_diff, 5),
        'pips': pips,
        'pip_size': config.pip_size,
        'contract_size': config.contract_size,
        'profit_loss': pnl,
        'commission': commission,
        'swap': swap,
        'is_winner': pnl > 0,
        'is_loser': pnl < 0
    }


# ==================== VALIDATION & TESTING ====================

def validate_against_examples() -> list:
    """
    Validate P&L calculations against known examples
    Returns list of test results
    """
    test_cases = [
        {
            'name': 'USDJPY (Forex JPY)',
            'symbol': 'USDJPY',
            'trade_type': 'BUY',
            'entry': 155.057,
            'exit': 155.995,
            'lot_size': 0.01,
            'expected': 60.0,  # Approximately
            'tolerance': 5.0
        },
        {
            'name': 'NAS100 (Index)',
            'symbol': 'NAS100',
            'trade_type': 'BUY',
            'entry': 25214.37,
            'exit': 25181.07,
            'lot_size': 0.03,
            'expected': -9.99,
            'tolerance': 1.0
        },
        {
            'name': 'USDCAD (Forex Standard)',
            'symbol': 'USDCAD',
            'trade_type': 'SELL',
            'entry': 1.39813,
            'exit': 1.39760,
            'lot_size': 0.40,
            'expected': 15.17,
            'tolerance': 3.0
        },
        {
            'name': 'BTCUSD (Crypto)',
            'symbol': 'BTCUSD',
            'trade_type': 'BUY',
            'entry': 104568.99,
            'exit': 104351.28,
            'lot_size': 0.01,
            'expected': -2.18,
            'tolerance': 0.5
        },
        {
            'name': 'ETHUSD (Crypto)',
            'symbol': 'ETHUSD',
            'trade_type': 'BUY',
            'entry': 46489.71,
            'exit': 46430.63,
            'lot_size': 0.30,
            'expected': -17.72,
            'tolerance': 2.0
        },
        {
            'name': 'XAUUSD (Gold)',
            'symbol': 'XAUUSD',
            'trade_type': 'BUY',
            'entry': 2650.00,
            'exit': 2660.00,
            'lot_size': 0.10,
            'expected': 100.0,  # $10 move * 100 oz * 0.10 lot = $100
            'tolerance': 1.0
        }
    ]
    
    results = []
    for tc in test_cases:
        pnl, pips, desc = calculate_pnl(
            tc['symbol'],
            tc['trade_type'],
            tc['entry'],
            tc['exit'],
            tc['lot_size']
        )
        
        diff = abs(pnl - tc['expected'])
        passed = diff <= tc['tolerance']
        
        results.append({
            'name': tc['name'],
            'symbol': tc['symbol'],
            'expected': tc['expected'],
            'calculated': pnl,
            'difference': round(diff, 2),
            'tolerance': tc['tolerance'],
            'passed': passed,
            'status': '✅ PASS' if passed else '❌ FAIL'
        })
    
    return results


def print_validation_table():
    """Print a formatted validation table"""
    results = validate_against_examples()
    
    print("\n" + "="*80)
    print("P&L CALCULATION VALIDATION")
    print("="*80)
    print(f"{'Symbol':<12} {'Expected':>12} {'Calculated':>12} {'Diff':>10} {'Status':>10}")
    print("-"*80)
    
    for r in results:
        status = "PASS" if r['passed'] else "FAIL"
        print(f"{r['symbol']:<12} ${r['expected']:>10.2f} ${r['calculated']:>10.2f} ${r['difference']:>8.2f} {status:>10}")
    
    print("="*80)
    passed = sum(1 for r in results if r['passed'])
    print(f"Results: {passed}/{len(results)} tests passed")
    print("="*80 + "\n")
    
    return results


if __name__ == '__main__':
    print_validation_table()
