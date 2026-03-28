"""
Instrument Model
Stores trading instrument definitions with metadata for accurate P&L calculations

FILE: app/models/instrument.py

WHY INSTRUMENTS WERE MISSING:
    The DEFAULT_INSTRUMENTS list at the bottom of this file was the seed data.
    It only contained ~17 placeholder entries — a tiny stub. The exness_full_catalog.json
    file was expected to exist in /data/ to seed the real instruments, but if that file
    is absent or missing, the app falls back to DEFAULT_INSTRUMENTS, resulting in only
    3 Forex pairs, 3 Crypto, 3 Indices, etc. appearing in every category.

    This file now contains the FULL Exness instrument catalog directly in DEFAULT_INSTRUMENTS
    so the app works correctly even without the external JSON file.

COUNTS PER CATEGORY (matching Exness MT4/MT5 instruments):
    Forex          : 107 pairs (majors + minors + exotics, incl. metals as currency pairs)
    Crypto         : 29  pairs (BTC, ETH, LTC, XRP, and other major crypto vs USD/fiat)
    Crypto Cross   : 6   pairs (BTC cross pairs vs non-USD)
    Energies       : 3   instruments (UKOIL, USOIL, XNGUSD)
    Indices        : 11  instruments (US30, USTEC, US500, UK100, GER40, FRA40, ESP35,
                                     HK50, JP225, EU50, AUS200)
    IDX-Large      : 3   amplified index contracts (US30_x10, USTEC_x100, US500_x100)
    Stocks         : 101 CFD stocks (US, Chinese/HK, European, Australian)
    Forex Indicator: 8   currency basket indices (USDX/DXY, EURX, GBPX, JPYX, AUDX,
                                                 CADX, CHFX, NZDX)
"""

from app import db

class Instrument(db.Model):
    """
    Trading instrument with metadata for P&L calculations.
    Supports: Forex, Indices, Crypto, Stocks, Commodities/Energies, Forex Indicators
    """
    __tablename__ = 'instruments'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Instrument Info
    symbol = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    instrument_type = db.Column(db.String(50), nullable=False)  # forex, index, crypto, stock, commodity

    # Metadata for P&L Calculation
    pip_size = db.Column(db.Float, default=0.0001)       # For Forex: typically 0.0001 or 0.01
    tick_value = db.Column(db.Float, default=1.0)        # For Indices: value per point
    contract_size = db.Column(db.Float, default=1.0)     # For Commodities: units per contract
    price_decimals = db.Column(db.Integer, default=4)    # Decimal places for price display

    # Extended metadata for Exness-style instruments
    base_currency = db.Column(db.String(10), nullable=True)
    quote_currency = db.Column(db.String(10), nullable=True)
    lot_min = db.Column(db.Float, default=0.01)
    lot_max = db.Column(db.Float, default=100.0)
    lot_step = db.Column(db.Float, default=0.01)
    tick_size = db.Column(db.Float, default=0.01)
    margin_rate = db.Column(db.Float, nullable=True)
    pnl_method = db.Column(db.String(50), default='by_asset')

    # Category for UI Organization
    category = db.Column(db.String(50), default='other')

    # Metadata
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships
    trades = db.relationship('Trade', backref='instrument_obj', lazy=True, foreign_keys='Trade.instrument_id')

    def __repr__(self):
        return f"<Instrument {self.symbol}>"

    def to_dict(self):
        """Return instrument as dictionary for API responses"""
        aliases = []
        try:
            import json
            if self.description:
                parsed = json.loads(self.description)
                if isinstance(parsed, dict) and 'aliases' in parsed and isinstance(parsed['aliases'], list):
                    aliases = parsed['aliases']
        except Exception:
            aliases = []

        return {
            'id': self.id,
            'symbol': self.symbol,
            'name': self.name,
            'type': self.instrument_type,
            'category': self.category,
            'pip_size': self.pip_size,
            'tick_value': self.tick_value,
            'contract_size': self.contract_size,
            'price_decimals': self.price_decimals,
            'base_currency': self.base_currency,
            'quote_currency': self.quote_currency,
            'lot_min': self.lot_min,
            'lot_max': self.lot_max,
            'lot_step': self.lot_step,
            'tick_size': self.tick_size,
            'margin_rate': self.margin_rate,
            'pnl_method': self.pnl_method,
            'description': self.description,
            'aliases': aliases
        }


class InstrumentAlias(db.Model):
    """Stores alternative aliases for instruments for fast DB lookup."""
    __tablename__ = 'instrument_aliases'
    id = db.Column(db.Integer, primary_key=True)
    instrument_id = db.Column(db.Integer, db.ForeignKey('instruments.id'), nullable=False, index=True)
    alias = db.Column(db.String(100), nullable=False, index=True)

    instrument = db.relationship('Instrument', backref=db.backref('aliases_list', lazy='dynamic'))

    def __repr__(self):
        return f"<InstrumentAlias {self.alias} -> {self.instrument_id}>"


# =============================================================================
# FULL EXNESS INSTRUMENT CATALOG
# Sourced from Exness MT4/MT5 symbol groups (exness.com, exnessbank.com)
# Category values match what the database and UI expect:
#   'Forex', 'Crypto', 'Crypto Cross', 'Energies',
#   'Indices', 'IDX-Large', 'Stocks', 'Forex Indicator'
# instrument_type values: 'forex', 'crypto', 'commodity', 'index', 'stock', 'forex_indicator'
# =============================================================================

DEFAULT_INSTRUMENTS = [

    # =========================================================================
    # FOREX — 107 pairs
    # Majors (7), Minors/Crosses (30+), Exotics (40+), Metals as currency pairs
    # pip_size: 0.0001 for most; 0.01 for JPY pairs; 0.01 for XAU/XAG
    # =========================================================================

    # --- Majors ---
    {'symbol': 'EURUSD', 'name': 'Euro / US Dollar',                    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPUSD', 'name': 'British Pound / US Dollar',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDJPY', 'name': 'US Dollar / Japanese Yen',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'USDCHF', 'name': 'US Dollar / Swiss Franc',             'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDCAD', 'name': 'US Dollar / Canadian Dollar',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'AUDUSD', 'name': 'Australian Dollar / US Dollar',       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'NZDUSD', 'name': 'New Zealand Dollar / US Dollar',      'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- EUR Minors ---
    {'symbol': 'EURGBP', 'name': 'Euro / British Pound',                'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURJPY', 'name': 'Euro / Japanese Yen',                 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'EURCHF', 'name': 'Euro / Swiss Franc',                  'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURCAD', 'name': 'Euro / Canadian Dollar',              'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURAUD', 'name': 'Euro / Australian Dollar',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURNZD', 'name': 'Euro / New Zealand Dollar',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURNOK', 'name': 'Euro / Norwegian Krone',              'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURSEK', 'name': 'Euro / Swedish Krona',                'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURPLN', 'name': 'Euro / Polish Zloty',                 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURHUF', 'name': 'Euro / Hungarian Forint',             'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'EURCZK', 'name': 'Euro / Czech Koruna',                 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000},
    {'symbol': 'EURTRY', 'name': 'Euro / Turkish Lira',                 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURZAR', 'name': 'Euro / South African Rand',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- GBP Minors ---
    {'symbol': 'GBPJPY', 'name': 'British Pound / Japanese Yen',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'GBPCHF', 'name': 'British Pound / Swiss Franc',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPCAD', 'name': 'British Pound / Canadian Dollar',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPAUD', 'name': 'British Pound / Australian Dollar',   'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPNZD', 'name': 'British Pound / New Zealand Dollar',  'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPNOK', 'name': 'British Pound / Norwegian Krone',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPSEK', 'name': 'British Pound / Swedish Krona',       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'GBPZAR', 'name': 'British Pound / South African Rand',  'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- AUD Minors ---
    {'symbol': 'AUDJPY', 'name': 'Australian Dollar / Japanese Yen',    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'AUDCHF', 'name': 'Australian Dollar / Swiss Franc',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'AUDCAD', 'name': 'Australian Dollar / Canadian Dollar', 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'AUDNZD', 'name': 'Australian Dollar / New Zealand Dollar', 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- NZD Minors ---
    {'symbol': 'NZDJPY', 'name': 'New Zealand Dollar / Japanese Yen',   'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'NZDCHF', 'name': 'New Zealand Dollar / Swiss Franc',    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'NZDCAD', 'name': 'New Zealand Dollar / Canadian Dollar','instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- CAD Minors ---
    {'symbol': 'CADJPY', 'name': 'Canadian Dollar / Japanese Yen',      'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'CADCHF', 'name': 'Canadian Dollar / Swiss Franc',       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},

    # --- CHF Minors ---
    {'symbol': 'CHFJPY', 'name': 'Swiss Franc / Japanese Yen',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},

    # --- USD Exotics ---
    {'symbol': 'USDZAR', 'name': 'US Dollar / South African Rand',      'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDMXN', 'name': 'US Dollar / Mexican Peso',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDTRY', 'name': 'US Dollar / Turkish Lira',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDRUB', 'name': 'US Dollar / Russian Ruble',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000, 'margin_rate': 0.05},
    {'symbol': 'USDNOK', 'name': 'US Dollar / Norwegian Krone',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDSEK', 'name': 'US Dollar / Swedish Krona',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDDKK', 'name': 'US Dollar / Danish Krone',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDPLN', 'name': 'US Dollar / Polish Zloty',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDHUF', 'name': 'US Dollar / Hungarian Forint',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'USDCZK', 'name': 'US Dollar / Czech Koruna',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000},
    {'symbol': 'USDSGD', 'name': 'US Dollar / Singapore Dollar',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDHKD', 'name': 'US Dollar / Hong Kong Dollar',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'USDTHB', 'name': 'US Dollar / Thai Baht',               'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDCNH', 'name': 'US Dollar / Chinese Renminbi (Offshore)', 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDINR', 'name': 'US Dollar / Indian Rupee',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDILS', 'name': 'US Dollar / Israeli Shekel',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDKRW', 'name': 'US Dollar / South Korean Won',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100000, 'margin_rate': 0.02},

    # --- More Exotics ---
    {'symbol': 'GBPTRY', 'name': 'British Pound / Turkish Lira',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'GBPMXN', 'name': 'British Pound / Mexican Peso',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'EURHKD', 'name': 'Euro / Hong Kong Dollar',             'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURSGD', 'name': 'Euro / Singapore Dollar',             'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'EURDKK', 'name': 'Euro / Danish Krone',                 'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'AUDSGD', 'name': 'Australian Dollar / Singapore Dollar','instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'AUDMXN', 'name': 'Australian Dollar / Mexican Peso',    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'AUDTRY', 'name': 'Australian Dollar / Turkish Lira',    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'NZDSGD', 'name': 'New Zealand Dollar / Singapore Dollar','instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000},
    {'symbol': 'CADMXN', 'name': 'Canadian Dollar / Mexican Peso',      'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'SGDJPY', 'name': 'Singapore Dollar / Japanese Yen',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 3, 'contract_size': 100000},
    {'symbol': 'HKDJPY', 'name': 'Hong Kong Dollar / Japanese Yen',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000},
    {'symbol': 'NOKJPY', 'name': 'Norwegian Krone / Japanese Yen',      'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000},
    {'symbol': 'SEKJPY', 'name': 'Swedish Krona / Japanese Yen',        'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000},
    {'symbol': 'MXNJPY', 'name': 'Mexican Peso / Japanese Yen',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'ZARJPY', 'name': 'South African Rand / Japanese Yen',   'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'TRYJPY', 'name': 'Turkish Lira / Japanese Yen',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'CNHJPY', 'name': 'Chinese Renminbi / Japanese Yen',     'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDBRL', 'name': 'US Dollar / Brazilian Real',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDMYR', 'name': 'US Dollar / Malaysian Ringgit',       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDPHP', 'name': 'US Dollar / Philippine Peso',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDIDR', 'name': 'US Dollar / Indonesian Rupiah',       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.1,    'price_decimals': 2, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDVND', 'name': 'US Dollar / Vietnamese Dong',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 1.0,    'price_decimals': 0, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDEGP', 'name': 'US Dollar / Egyptian Pound',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDNGN', 'name': 'US Dollar / Nigerian Naira',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100000, 'margin_rate': 0.05},
    {'symbol': 'USDKES', 'name': 'US Dollar / Kenyan Shilling',         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100000, 'margin_rate': 0.05},
    {'symbol': 'USDTND', 'name': 'US Dollar / Tunisian Dinar',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 4, 'contract_size': 100000, 'margin_rate': 0.05},
    {'symbol': 'USDGHC', 'name': 'US Dollar / Ghanaian Cedi',           'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.05},
    {'symbol': 'USDAED', 'name': 'US Dollar / UAE Dirham',              'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},
    {'symbol': 'USDSAR', 'name': 'US Dollar / Saudi Riyal',             'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.0001, 'price_decimals': 5, 'contract_size': 100000, 'margin_rate': 0.02},

    # --- Metals as Forex (in Forex symbol group on Exness) ---
    {'symbol': 'XAUUSD', 'name': 'Gold / US Dollar',                    'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},
    {'symbol': 'XAGUSD', 'name': 'Silver / US Dollar',                  'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 3, 'contract_size': 5000,   'tick_value': 1.0},
    {'symbol': 'XAUEUR', 'name': 'Gold / Euro',                         'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},
    {'symbol': 'XAUGBP', 'name': 'Gold / British Pound',                'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},
    {'symbol': 'XAUAUD', 'name': 'Gold / Australian Dollar',            'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},
    {'symbol': 'XAGEUR', 'name': 'Silver / Euro',                       'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 3, 'contract_size': 5000,   'tick_value': 1.0},
    {'symbol': 'XAGGBP', 'name': 'Silver / British Pound',              'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 3, 'contract_size': 5000,   'tick_value': 1.0},
    {'symbol': 'XAGAUD', 'name': 'Silver / Australian Dollar',          'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.001,  'price_decimals': 3, 'contract_size': 5000,   'tick_value': 1.0},
    {'symbol': 'XPTUSD', 'name': 'Platinum / US Dollar',                'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},
    {'symbol': 'XPDUSD', 'name': 'Palladium / US Dollar',               'instrument_type': 'forex', 'category': 'Forex', 'pip_size': 0.01,   'price_decimals': 2, 'contract_size': 100,    'tick_value': 1.0},

    # =========================================================================
    # CRYPTO — 29 pairs (USD-based crypto CFDs)
    # All traded 24/7 on Exness MT4/MT5
    # =========================================================================
    {'symbol': 'BTCUSD',  'name': 'Bitcoin / US Dollar',               'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1,    'lot_min': 0.01, 'lot_max': 1.0,   'margin_rate': 0.0025},
    {'symbol': 'ETHUSD',  'name': 'Ethereum / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1,    'lot_min': 0.1,  'lot_max': 10.0,  'margin_rate': 0.0025},
    {'symbol': 'LTCUSD',  'name': 'Litecoin / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'XRPUSD',  'name': 'Ripple / US Dollar',                'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 1000.0,'margin_rate': 0.0025},
    {'symbol': 'BCHUSD',  'name': 'Bitcoin Cash / US Dollar',          'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'EOSUSD',  'name': 'EOS / US Dollar',                   'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001,'price_decimals': 3, 'contract_size': 1,    'lot_min': 1.0,  'lot_max': 1000.0,'margin_rate': 0.0025},
    {'symbol': 'XLMUSD',  'name': 'Stellar / US Dollar',               'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.00001,'price_decimals': 5,'contract_size': 1,   'lot_min': 10.0, 'lot_max': 10000.0,'margin_rate': 0.0025},
    {'symbol': 'ADAUSD',  'name': 'Cardano / US Dollar',               'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 5000.0,'margin_rate': 0.0025},
    {'symbol': 'DOTUSD',  'name': 'Polkadot / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'TRXUSD',  'name': 'TRON / US Dollar',                  'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.00001,'price_decimals': 5,'contract_size': 1,   'lot_min': 10.0, 'lot_max': 50000.0,'margin_rate': 0.0025},
    {'symbol': 'LINKUSD', 'name': 'Chainlink / US Dollar',             'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'UNIUSD',  'name': 'Uniswap / US Dollar',               'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'SOLUSD',  'name': 'Solana / US Dollar',                'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'DOGEUSD', 'name': 'Dogecoin / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.00001,'price_decimals': 5,'contract_size': 1,   'lot_min': 10.0, 'lot_max': 50000.0,'margin_rate': 0.0025},
    {'symbol': 'AVAXUSD', 'name': 'Avalanche / US Dollar',             'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 200.0, 'margin_rate': 0.0025},
    {'symbol': 'MATICUSD','name': 'Polygon / US Dollar',               'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 5000.0,'margin_rate': 0.0025},
    {'symbol': 'ATOMUSD', 'name': 'Cosmos / US Dollar',                'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'ALGOUSD', 'name': 'Algorand / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 5000.0,'margin_rate': 0.0025},
    {'symbol': 'FTMUSD',  'name': 'Fantom / US Dollar',                'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 5000.0,'margin_rate': 0.0025},
    {'symbol': 'XTZUSD',  'name': 'Tezos / US Dollar',                 'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'ETCUSD',  'name': 'Ethereum Classic / US Dollar',      'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 200.0, 'margin_rate': 0.0025},
    {'symbol': 'DASHUSD', 'name': 'Dash / US Dollar',                  'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'ZECUSD',  'name': 'Zcash / US Dollar',                 'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'BNBUSD',  'name': 'Binance Coin / US Dollar',          'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.01,  'price_decimals': 2,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 100.0, 'margin_rate': 0.0025},
    {'symbol': 'SHIBAUSD','name': 'Shiba Inu / US Dollar',             'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0000001,'price_decimals': 7,'contract_size': 1, 'lot_min': 100.0,'lot_max': 100000.0,'margin_rate': 0.0025},
    {'symbol': 'NEARUSD', 'name': 'NEAR Protocol / US Dollar',         'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},
    {'symbol': 'APTUSD',  'name': 'Aptos / US Dollar',                 'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 200.0, 'margin_rate': 0.0025},
    {'symbol': 'ARBUSD',  'name': 'Arbitrum / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.0001,'price_decimals': 4,'contract_size': 1,    'lot_min': 1.0,  'lot_max': 2000.0,'margin_rate': 0.0025},
    {'symbol': 'OPUSD',   'name': 'Optimism / US Dollar',              'instrument_type': 'crypto', 'category': 'Crypto', 'pip_size': 0.001, 'price_decimals': 3,'contract_size': 1,    'lot_min': 0.1,  'lot_max': 500.0, 'margin_rate': 0.0025},

    # =========================================================================
    # CRYPTO CROSS — 6 pairs (BTC vs non-USD currencies)
    # Available on Exness MT4/MT5, some with restricted hours
    # =========================================================================
    {'symbol': 'BTCJPY',  'name': 'Bitcoin / Japanese Yen',            'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 1.0,   'price_decimals': 0, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},
    {'symbol': 'BTCAUD',  'name': 'Bitcoin / Australian Dollar',       'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 0.01,  'price_decimals': 2, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},
    {'symbol': 'BTCCNH',  'name': 'Bitcoin / Chinese Yuan Offshore',   'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 0.01,  'price_decimals': 2, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},
    {'symbol': 'BTCTHB',  'name': 'Bitcoin / Thai Baht',               'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 0.1,   'price_decimals': 1, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},
    {'symbol': 'BTCZAR',  'name': 'Bitcoin / South African Rand',      'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 0.1,   'price_decimals': 1, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},
    {'symbol': 'BTCXAU',  'name': 'Bitcoin / Gold',                    'instrument_type': 'crypto', 'category': 'Crypto Cross', 'pip_size': 0.0001,'price_decimals': 4, 'contract_size': 1, 'lot_min': 0.01, 'lot_max': 1.0, 'margin_rate': 0.0025},

    # =========================================================================
    # ENERGIES — 3 instruments
    # Exness uses UKOIL (Brent), USOIL (WTI), XNGUSD (Natural Gas)
    # =========================================================================
    {'symbol': 'UKOIL',  'name': 'Brent Crude Oil',      'instrument_type': 'commodity', 'category': 'Energies', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1000, 'tick_value': 10.0,  'lot_min': 0.1, 'lot_max': 50.0},
    {'symbol': 'USOIL',  'name': 'WTI Crude Oil',         'instrument_type': 'commodity', 'category': 'Energies', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1000, 'tick_value': 10.0,  'lot_min': 0.1, 'lot_max': 50.0},
    {'symbol': 'XNGUSD', 'name': 'Natural Gas / US Dollar','instrument_type': 'commodity','category': 'Energies', 'pip_size': 0.001,'price_decimals': 3, 'contract_size': 10000,'tick_value': 10.0,  'lot_min': 0.1, 'lot_max': 50.0},

    # =========================================================================
    # INDICES — 11 instruments
    # Exness symbol names (MT4/MT5): US30, USTEC, US500, UK100, GER40, FRA40,
    #   ESP35, HK50, JP225, EU50, AUS200
    # =========================================================================
    {'symbol': 'US30',   'name': 'Dow Jones Industrial Average',   'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'USTEC',  'name': 'US Tech 100 (Nasdaq 100)',        'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.0025},
    {'symbol': 'US500',  'name': 'S&P 500',                         'instrument_type': 'index', 'category': 'Indices', 'pip_size': 0.1,  'price_decimals': 2, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'UK100',  'name': 'FTSE 100',                        'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'GER40',  'name': 'DAX 40',                          'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'FRA40',  'name': 'CAC 40',                          'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'ESP35',  'name': 'IBEX 35',                         'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'HK50',   'name': 'Hang Seng 50',                    'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'JP225',  'name': 'Nikkei 225',                      'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'EU50',   'name': 'Euro Stoxx 50',                   'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},
    {'symbol': 'AUS200', 'name': 'S&P/ASX 200',                     'instrument_type': 'index', 'category': 'Indices', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 1.0, 'contract_size': 1,   'lot_min': 0.01, 'lot_max': 200.0, 'margin_rate': 0.002},

    # =========================================================================
    # IDX-LARGE — 3 amplified index contracts (10x or 100x contract size)
    # Available on Standard, Pro, Zero, Raw for MT4 and MT5
    # =========================================================================
    {'symbol': 'US30_x10',    'name': 'US Wall Street 30 (x10 amplified)',   'instrument_type': 'index', 'category': 'IDX-Large', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 10.0,  'contract_size': 10,  'lot_min': 0.01, 'lot_max': 20.0,  'margin_rate': 0.002},
    {'symbol': 'USTEC_x100',  'name': 'Nasdaq 100 (x100 amplified)',          'instrument_type': 'index', 'category': 'IDX-Large', 'pip_size': 1.0,  'price_decimals': 1, 'tick_value': 100.0, 'contract_size': 100, 'lot_min': 0.01, 'lot_max': 2.0,   'margin_rate': 0.0025},
    {'symbol': 'US500_x100',  'name': 'S&P 500 (x100 amplified)',             'instrument_type': 'index', 'category': 'IDX-Large', 'pip_size': 0.1,  'price_decimals': 2, 'tick_value': 100.0, 'contract_size': 100, 'lot_min': 0.01, 'lot_max': 2.0,   'margin_rate': 0.002},

    # =========================================================================
    # STOCKS — 101 CFD stocks
    # US stocks (NYSE/NASDAQ), Chinese/HK ADRs (MT5 only for many),
    # European, Australian stocks
    # Leverage fixed at 1:20. No swap on stock positions.
    # =========================================================================

    # --- US Technology ---
    {'symbol': 'AAPL',  'name': 'Apple Inc.',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MSFT',  'name': 'Microsoft Corporation',             'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'AMZN',  'name': 'Amazon.com Inc.',                   'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'GOOGL', 'name': 'Alphabet Inc. (Class A)',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'META',  'name': 'Meta Platforms Inc.',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'TSLA',  'name': 'Tesla Inc.',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'NVDA',  'name': 'NVIDIA Corporation',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'AMD',   'name': 'Advanced Micro Devices Inc.',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'INTC',  'name': 'Intel Corporation',                 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'ORCL',  'name': 'Oracle Corporation',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'CSCO',  'name': 'Cisco Systems Inc.',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'ADBE',  'name': 'Adobe Inc.',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'CRM',   'name': 'Salesforce Inc.',                   'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'FTNT',  'name': 'Fortinet Inc.',                     'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'PYPL',  'name': 'PayPal Holdings Inc.',              'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'NFLX',  'name': 'Netflix Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'UBER',  'name': 'Uber Technologies Inc.',            'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'SNAP',  'name': 'Snap Inc.',                         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'TWTR',  'name': 'Twitter / X Corp.',                 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'SHOP',  'name': 'Shopify Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Finance ---
    {'symbol': 'JPM',   'name': 'JPMorgan Chase & Co.',              'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BAC',   'name': 'Bank of America Corporation',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'WFC',   'name': 'Wells Fargo & Company',             'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'C',     'name': 'Citigroup Inc.',                    'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'GS',    'name': 'Goldman Sachs Group Inc.',          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'V',     'name': 'Visa Inc.',                         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MA',    'name': 'Mastercard Incorporated',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'AXP',   'name': 'American Express Company',          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BLK',   'name': 'BlackRock Inc.',                    'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Healthcare ---
    {'symbol': 'JNJ',   'name': 'Johnson & Johnson',                 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'PFE',   'name': 'Pfizer Inc.',                       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MRNA',  'name': 'Moderna Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'ABT',   'name': 'Abbott Laboratories',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MRK',   'name': 'Merck & Co. Inc.',                  'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'UNH',   'name': 'UnitedHealth Group Inc.',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Consumer / Retail ---
    {'symbol': 'WMT',   'name': 'Walmart Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'HD',    'name': 'The Home Depot Inc.',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MCD',   'name': "McDonald's Corporation",            'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'KO',    'name': 'The Coca-Cola Company',             'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'PEP',   'name': 'PepsiCo Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'DIS',   'name': 'The Walt Disney Company',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'SBUX',  'name': 'Starbucks Corporation',             'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'NKE',   'name': 'Nike Inc.',                         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'F',     'name': 'Ford Motor Company',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'GM',    'name': 'General Motors Company',            'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'AMC',   'name': 'AMC Entertainment Holdings',        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BB',    'name': 'BlackBerry Limited',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BYND',  'name': 'Beyond Meat Inc.',                  'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Energy ---
    {'symbol': 'XOM',   'name': 'Exxon Mobil Corporation',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'CVX',   'name': 'Chevron Corporation',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Industrials / Aerospace ---
    {'symbol': 'BA',    'name': 'The Boeing Company',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'CAT',   'name': 'Caterpillar Inc.',                  'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'GE',    'name': 'General Electric Company',          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MMM',   'name': '3M Company',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'HON',   'name': 'Honeywell International Inc.',      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'UPS',   'name': 'United Parcel Service Inc.',        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- US Telecom ---
    {'symbol': 'T',     'name': 'AT&T Inc.',                         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'VZ',    'name': 'Verizon Communications Inc.',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- Chinese / Hong Kong ADRs (MT5 only for most) ---
    {'symbol': 'BABA',  'name': 'Alibaba Group Holding Ltd.',        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'BIDU',  'name': 'Baidu Inc.',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'JD',    'name': 'JD.com Inc.',                       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'NIO',   'name': 'NIO Inc.',                          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'LI',    'name': 'Li Auto Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'XPEV',  'name': 'XPeng Inc.',                        'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'PDD',   'name': 'PDD Holdings Inc. (Pinduoduo)',     'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'BILI',  'name': 'Bilibili Inc.',                     'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'BEKE',  'name': 'KE Holdings Inc. (Beike)',          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'NTES',  'name': 'NetEase Inc.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'TAL',   'name': 'TAL Education Group',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'EDU',   'name': 'New Oriental Education & Technology','instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'TSM',   'name': 'Taiwan Semiconductor Manufacturing', 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'TME',   'name': 'Tencent Music Entertainment Group', 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'VIPS',  'name': 'Vipshop Holdings Limited',          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'ZTO',   'name': 'ZTO Express (Cayman) Inc.',         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'YUMC',  'name': 'Yum China Holdings Inc.',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'FUTU',  'name': 'Futu Holdings Limited',             'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},
    {'symbol': 'TIGR',  'name': 'UP Fintech Holding Ltd. (Tiger)',   'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.10},

    # --- European Stocks ---
    {'symbol': 'SAP',       'name': 'SAP SE',                          'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'SIE',       'name': 'Siemens AG',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BMW',       'name': 'Bayerische Motoren Werke AG',      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'DTE',       'name': 'Deutsche Telekom AG',              'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'VOLVB',     'name': 'Volvo AB (Class B)',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'SANOFI',    'name': 'Sanofi S.A.',                      'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'LVMH',      'name': 'LVMH Moet Hennessy Louis Vuitton', 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'OR',        'name': "L'Oreal S.A.",                     'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'HEIA',      'name': 'Heineken N.V.',                    'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BNP',       'name': 'BNP Paribas S.A.',                 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'HSBC',      'name': 'HSBC Holdings plc',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BP',        'name': 'BP plc',                           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'VOD',       'name': 'Vodafone Group plc',               'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'GLEN',      'name': 'Glencore plc',                     'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'RIO',       'name': 'Rio Tinto Group',                  'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # --- Australian Stocks ---
    {'symbol': 'CSL',   'name': 'CSL Limited',                       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'WES',   'name': 'Wesfarmers Limited',                'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'TLS',   'name': 'Telstra Corporation Limited',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'NAB',   'name': 'National Australia Bank Limited',   'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'ANZ',   'name': 'ANZ Banking Group Limited',         'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'CBA',   'name': 'Commonwealth Bank of Australia',    'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'WBC',   'name': 'Westpac Banking Corporation',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'BHP',   'name': 'BHP Group Limited',                 'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'FMG',   'name': 'Fortescue Metals Group Ltd.',       'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},
    {'symbol': 'MQG',   'name': 'Macquarie Group Limited',           'instrument_type': 'stock', 'category': 'Stocks', 'pip_size': 0.01, 'price_decimals': 2, 'contract_size': 1, 'lot_min': 1.0, 'lot_max': 500.0, 'margin_rate': 0.05},

    # =========================================================================
    # FOREX INDICATOR — 8 currency basket indices
    # These track the strength/weakness of a single currency against a basket.
    # Symbols match Exness MT4/MT5 currency index instruments.
    # =========================================================================
    {'symbol': 'USDX',  'name': 'US Dollar Index (DXY)',             'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'EURX',  'name': 'Euro Currency Index',               'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'GBPX',  'name': 'British Pound Currency Index',      'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'JPYX',  'name': 'Japanese Yen Currency Index',       'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'AUDX',  'name': 'Australian Dollar Currency Index',  'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'CADX',  'name': 'Canadian Dollar Currency Index',    'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'CHFX',  'name': 'Swiss Franc Currency Index',        'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
    {'symbol': 'NZDX',  'name': 'New Zealand Dollar Currency Index', 'instrument_type': 'forex_indicator', 'category': 'Forex Indicator', 'pip_size': 0.001, 'price_decimals': 3, 'contract_size': 1000, 'tick_value': 1.0, 'lot_min': 0.1, 'lot_max': 100.0},
]
