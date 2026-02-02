"""
Instrument Model
Stores trading instrument definitions with metadata for accurate P&L calculations
"""

from app import db

class Instrument(db.Model):
    """
    Trading instrument with metadata for P&L calculations.
    
    Supports: Forex, Indices, Crypto, Stocks, Commodities
    """
    __tablename__ = 'instruments'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Instrument Info
    symbol = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    instrument_type = db.Column(db.String(50), nullable=False)  # forex, index, crypto, stock, commodity
    
    # Metadata for P&L Calculation
    pip_size = db.Column(db.Float, default=0.0001)  # For Forex: typically 0.0001 or 0.01
    tick_value = db.Column(db.Float, default=1.0)   # For Indices: value per point
    contract_size = db.Column(db.Float, default=1.0)  # For Commodities: units per contract
    price_decimals = db.Column(db.Integer, default=4)  # Decimal places for price display
    
    # Category for UI Organization
    category = db.Column(db.String(50), default='other')  # forex, index, crypto, stock, commodity
    
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
        # Attempt to load aliases from JSON stored in description if present
        aliases = []
        try:
            import json
            if self.description:
                parsed = json.loads(self.description)
                if isinstance(parsed, dict) and 'aliases' in parsed and isinstance(parsed['aliases'], list):
                    aliases = parsed['aliases']
        except Exception:
            # ignore parse errors and fall back to empty aliases
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


# Default instruments to seed
DEFAULT_INSTRUMENTS = [
    # Forex Major Pairs
    {'symbol': 'EURUSD', 'name': 'Euro / US Dollar', 'type': 'forex', 'category': 'forex', 'pip_size': 0.0001, 'price_decimals': 4},
    {'symbol': 'GBPUSD', 'name': 'British Pound / US Dollar', 'type': 'forex', 'category': 'forex', 'pip_size': 0.0001, 'price_decimals': 4},
    {'symbol': 'USDJPY', 'name': 'US Dollar / Japanese Yen', 'type': 'forex', 'category': 'forex', 'pip_size': 0.01, 'price_decimals': 2},
    {'symbol': 'AUDUSD', 'name': 'Australian Dollar / US Dollar', 'type': 'forex', 'category': 'forex', 'pip_size': 0.0001, 'price_decimals': 4},
    
    # Indices
    {'symbol': 'SPX', 'name': 'S&P 500', 'type': 'index', 'category': 'index', 'tick_value': 1.0, 'price_decimals': 2},
    {'symbol': 'NDX', 'name': 'Nasdaq 100', 'type': 'index', 'category': 'index', 'tick_value': 1.0, 'price_decimals': 2},
    {'symbol': 'FTSE', 'name': 'FTSE 100', 'type': 'index', 'category': 'index', 'tick_value': 1.0, 'price_decimals': 2},
    
    # Crypto
    {'symbol': 'BTCUSD', 'name': 'Bitcoin / US Dollar', 'type': 'crypto', 'category': 'crypto', 'price_decimals': 2},
    {'symbol': 'ETHUSD', 'name': 'Ethereum / US Dollar', 'type': 'crypto', 'category': 'crypto', 'price_decimals': 2},
    {'symbol': 'XRPUSD', 'name': 'Ripple / US Dollar', 'type': 'crypto', 'category': 'crypto', 'price_decimals': 4},
    
    # Commodities
    {'symbol': 'XAUUSD', 'name': 'Gold / US Dollar', 'type': 'commodity', 'category': 'commodity', 'pip_size': 0.01, 'contract_size': 100, 'price_decimals': 2},
    {'symbol': 'XAGUSD', 'name': 'Silver / US Dollar', 'type': 'commodity', 'category': 'commodity', 'pip_size': 0.01, 'contract_size': 5000, 'price_decimals': 2},
    {'symbol': 'WTIUSD', 'name': 'WTI Crude Oil', 'type': 'commodity', 'category': 'commodity', 'pip_size': 0.01, 'contract_size': 1000, 'price_decimals': 2},
    
    # Stocks (examples)
    {'symbol': 'AAPL', 'name': 'Apple Inc.', 'type': 'stock', 'category': 'stock', 'price_decimals': 2},
    {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'type': 'stock', 'category': 'stock', 'price_decimals': 2},
    {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'type': 'stock', 'category': 'stock', 'price_decimals': 2},
    {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'type': 'stock', 'category': 'stock', 'price_decimals': 2},
]
