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
