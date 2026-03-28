# Changelog

## 2025-12-12 - Broker Profiles, Instrument Catalog, P&L Engine, Importers

- Added a production-ready Broker Profile System skeleton:
  - `app/models/broker.py` (SQLAlchemy models)
  - Alembic migration stub: `migrations/versions/20251212_add_broker_tables.py`
  - API endpoints: `app/routes/brokers.py`, `app/routes/imports.py`
- Instrument catalog and mapping:
  - `data/brokers.json` seeded with 10 brokers
  - `data/instruments.json` (small sample). Use `scripts/generate_instruments_json.py` to generate 2,500+ instruments programmatically.
  - `app/services/instrument_catalog.py` for loading and searching the catalog
  - `app/mappers/instrument_mapper.py` to map broker symbols to canonical symbols
- P&L engine:
  - `app/services/pnl_engine.py` multi-asset P&L calculation
  - Unit tests added: `tests/test_pnl_engine.py`, `tests/test_instrument_mapper.py`, `tests/test_instrument_search.py`
- Importer placeholders:
  - `app/importers/csv_importer.py`, `mt5_parser.py`, `oanda.py`, `binance.py`
  - Upload endpoint: `app/routes/imports.py`
- Scripts:
  - `scripts/generate_instruments_json.py` - create a 2,500+ instruments JSON file
  - `scripts/seed_instruments.py` - seed DB from `data/instruments.json`

See README or run `python scripts/generate_instruments_json.py` to create the full instruments dataset, then run the seed script to load into the DB.
