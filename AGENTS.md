# AGENTS.md - TradeVerse

## Commands
- **Run app**: `python run.py` (serves at http://localhost:5000)
- **Initialize DB**: `flask init_db`
- **Reset DB**: `flask reset_db`
- **Run migrations**: `flask db upgrade`

## Architecture
- **Framework**: Flask 3.0 with Application Factory pattern (`app/__init__.py`)
- **Database**: SQLAlchemy with SQLite (dev) / configurable via DATABASE_URL
- **Auth**: Flask-Login + Flask-Bcrypt for password hashing
- **Forms**: Flask-WTF with CSRF protection
- **Structure**: Blueprints in `app/routes/` (auth, main, trade, dashboard, planner)
- **Models**: `app/models/` (User, Trade, TradePlan) - SQLAlchemy ORM
- **Templates**: Jinja2 in `app/templates/`, static files in `app/static/`

## Code Style
- Use docstrings for modules, classes, and methods
- Imports: stdlib → third-party (flask, sqlalchemy) → local (`from app import`)
- Models use `__tablename__`, grouped columns with comment headers
- Routes use Flask Blueprints with `bp = Blueprint('name', __name__)`
- Config via environment variables loaded from `.env` (python-dotenv)
- Passwords hashed via `bcrypt.generate_password_hash()`, never stored plain
- Return `render_template()` for views, use flash messages for user feedback

## Recent Instrument & UI Fixes (2026-02-23)

Summary:
- Fixed instrument picker category parsing and icon mapping so categories like "Crypto Cross", "Energies", "Forex Indicator", "IDX-Large" and "Indices" show meaningful, professional icons instead of question marks.
- Made the instrument list rendering robust to API response shapes (accepts wrapped responses {success, results}) and added defensive handling to remove console errors.
- Ensured category query strings are URL-encoded and active tab toggling is safe for special characters.
- Added a small selected-instrument code display in the Add Trade card header which updates when a user picks an instrument.
- Added server-side endpoints for diagnostics: `/api/db/instruments/counts` and a safe simulated `/api/db/instruments/quotes` to power a lightweight rotating quotes widget.
- Added a live-rotating quotes widget in the navbar (client fetch + smooth fade/rotate) for premium UX; it's non-invasive and uses a simulated feed by default.

What changed (files):
- `app/static/js/instrument-picker-simple.js` — robust category parsing, icon mapping, safe selection updates, encoded queries, empty-state UI.
- `app/templates/trade/add.html` — header instrument code display, safer event binding for R:R inputs.
- `app/routes/api_instruments.py` — added counts & quotes endpoints (non-destructive simulation endpoint).
- `app/templates/base.html` — navbar quotes container, CSS and JS rotation logic.
- `scripts/instrument_counts.py` — dev helper to report totals and sample symbols.

DB snapshot (dev run):
- Total active instruments found: 333
- Counts by category: Crypto:17, Crypto Cross:3, Energies:3, Forex:140, Forex Indicator:55, IDX-Large:3, Indices:11, Stocks:101

Notes & Next steps:
- The quotes endpoint is intentionally simulated — replace with your live feed when ready (non-breaking).
- I added defensive guards to remove common console errors; please test in browser to validate no runtime console errors remain.
- If you want, I can implement virtualization/virtual-scrolling for very large lists, or replace the simulated feed with an actual market data source.

