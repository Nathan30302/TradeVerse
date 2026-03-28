# P&L Calculation Fix - TODO List

## Task: Fix P&L calculation to match Exness instrument behavior

### Files to Create:
- [x] 1. Create new unified Exness P&L calculator service
- [ ] 2. Update Trade model to use new P&L service

### New Service: app/services/exness_pnl_calculator.py
- [x] Create ExnessPnLCalculator class
- [x] Implement category-specific formulas:
  - [x] Forex: use contract_size * price_diff * lot_size
  - [x] Crypto: quantity * price_diff (1 lot = 1 unit)
  - [x] Crypto Cross: same as crypto
  - [x] Indices: tick_value * points * lots
  - [x] IDX-Large: amplified contract (10x, 100x)
  - [x] Stocks: shares * price_diff
  - [x] Energies: contract_size * price_diff * lots
  - [x] Forex Indicator: contract_size * price_diff * lots

### Update: app/models/trade.py
- [ ] Import new P&L calculator
- [ ] Update calculate_pnl() method

### Verification:
- [ ] Test Forex pair (EURUSD, USDJPY)
- [ ] Test Crypto (BTCUSD)
- [ ] Test Index (US500)
- [ ] Test Stock (AAPL)
- [ ] Test Energy (USOIL)
- [ ] Verify BUY and SELL both work

### Expected Results:
- Forex: ~$10 per pip per standard lot
- Crypto: price_diff * lot_size
- Index: tick_value * price_diff * lots
- Stock: price_diff * shares
- Energy: contract_size * price_diff * lots

