# Instrument System - Quick Reference

## 🚀 Quick Start

```bash
# 1. Start the app
python run.py

# 2. Test the API
curl http://localhost:5000/api/instruments

# 3. Search for an instrument
curl "http://localhost:5000/api/instruments?search=btc"

# 4. Calculate P&L
curl -X POST http://localhost:5000/api/calculate-pnl \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_id": 1,
    "entry_price": 1.2000,
    "exit_price": 1.2050,
    "lot_size": 1.0,
    "trade_type": "BUY"
  }'
```

## 📦 Components

### Backend
- `app/models/instrument.py` - Instrument model with metadata
- `app/services/pnl_calculator_advanced.py` - Type-specific P&L calculations
- `app/routes/instruments.py` - `/api/instruments` endpoints
- `app/routes/main.py` - `/api/calculate-pnl` endpoint

### Frontend
- `app/static/js/instrument-picker.js` - Real-time search + calculation
- `app/static/css/instrument-picker.css` - Theme-compatible styling

## 🎯 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/instruments` | List all instruments |
| GET | `/api/instruments?search=TERM` | Search instruments |
| GET | `/api/instruments?category=forex` | Filter by category |
| GET | `/api/instruments/<id>` | Get single instrument |
| GET | `/api/instruments/by-symbol/EURUSD` | Get by symbol |
| GET | `/api/instruments/categories` | Get category counts |
| POST | `/api/calculate-pnl` | Calculate P&L |

## 🔢 Supported Instruments (17 Total)

**Forex (4)**
- EURUSD, GBPUSD, USDJPY, AUDUSD

**Indices (3)**
- SPX, NDX, FTSE

**Crypto (3)**
- BTCUSD, ETHUSD, XRPUSD

**Commodities (3)**
- XAUUSD (Gold), XAGUSD (Silver), WTIUSD (Oil)

**Stocks (4)**
- AAPL, MSFT, GOOGL, TSLA

## 💡 Usage Examples

### Search for Gold
```bash
curl "http://localhost:5000/api/instruments?search=gold"
```

### Get All Forex Instruments
```bash
curl "http://localhost:5000/api/instruments?category=forex"
```

### Calculate Forex P&L
```bash
# Entry: 1.2000, Exit: 1.2050, Qty: 1.0 lot
# Expected: 50 pips = $500 profit
curl -X POST http://localhost:5000/api/calculate-pnl \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_id": 1,
    "entry_price": 1.2000,
    "exit_price": 1.2050,
    "lot_size": 1.0,
    "trade_type": "BUY"
  }'
# Response: {"profit_loss": 0.05, "pips_or_points": 50.0, ...}
```

### JavaScript Usage
```javascript
// Initialize picker
const picker = new InstrumentPicker();

// Initialize calculator
const calculator = new TradeCalculator();

// Access selected instrument
console.log(picker.selectedInstrument);
```

## 🎨 HTML Integration

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/instrument-picker.css') }}">

<div class="instrument-picker-container">
    <input type="text" id="instrument-search" placeholder="Search instruments...">
    <div id="instrument-dropdown"></div>
</div>

<input type="hidden" id="instrument_id" name="instrument_id">
<input type="hidden" id="symbol" name="symbol">

<div id="pnl-display"></div>

<script src="{{ url_for('static', filename='js/instrument-picker.js') }}"></script>
```

## 🧪 Run Tests

```bash
# Integration tests
python test_instrument_system.py

# Expected: ALL TESTS PASSED [OK]
```

## 📊 P&L Formula Examples

### Forex (EURUSD)
```
Entry: 1.2000, Exit: 1.2050, Qty: 1.0 lot
Price Diff: 0.0050
Pips: 0.0050 / 0.0001 = 50 pips
P&L: 50 * 0.0001 * 10 * 1 = 0.05 (i.e., $500)
```

### Index (SPX)
```
Entry: 4000, Exit: 4010, Qty: 1 contract
Points: 10
P&L: 10 * 1.0 * 1 = 10
```

### Crypto (BTCUSD)
```
Entry: 43000, Exit: 43500, Qty: 0.1 BTC
Price Diff: 500
P&L: 500 * 0.1 = 50
```

### Stock (AAPL)
```
Entry: 150, Exit: 152, Qty: 10 shares
Price Diff: 2
P&L: 2 * 10 = 20
```

### Commodity (Gold)
```
Entry: 1950, Exit: 1960, Qty: 1 contract (100 oz)
Price Diff: 10
P&L: 10 * 100 * 1 = 1000
```

## 🔄 Reverse P&L Calculation

Find exit price from target P&L:
```python
calc = PnLCalculator(InstrumentType.FOREX, pip_size=0.0001)
exit_price = calc.reverse_calculate_exit(
    entry_price=1.2000,
    qty=1.0,
    target_pnl=0.05,  # $500 in real terms
    trade_type='BUY'
)
# Returns: 1.2050
```

## ⚙️ Add Custom Instrument

In `app/models/instrument.py`:
```python
DEFAULT_INSTRUMENTS = [
    # ... existing instruments ...
    {
        'symbol': 'CUSTOM',
        'name': 'My Custom Instrument',
        'type': 'crypto',  # forex, index, crypto, stock, commodity
        'category': 'crypto',
        'pip_size': 0.00000001,
        'tick_value': 1.0,
        'contract_size': 1.0,
        'price_decimals': 8
    }
]
```

## 🎨 Theme Support

The component automatically adapts to light/dark/blue themes:

```css
/* Light Mode (default) */
#instrument-search {
    background: #ffffff;
    color: #333333;
}

/* Dark Mode */
:root.dark #instrument-search {
    background: #2a2a2a;
    color: #e0e0e0;
}

/* Blue Mode */
:root.blue #instrument-search {
    background: #f0f4ff;
    color: #0033cc;
}
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Instruments not loading | Ensure `/api/instruments` is accessible |
| P&L calculation wrong | Check instrument metadata (pip_size, tick_value) |
| Theme not applying | Make sure `instrument-picker.css` is loaded before JS |
| Search not working | Check browser console for JavaScript errors |
| CSRF error on POST | Verify CSRF token is in hidden form field |

## 📞 Contact

Questions? Check the detailed documentation:
- `INSTRUMENT_SYSTEM_SUMMARY.md` - Full feature documentation
- `DEPLOYMENT_SUMMARY.md` - Deployment & integration guide

---

**Version**: 1.0  
**Status**: Production Ready ✓  
**Last Updated**: December 11, 2025
