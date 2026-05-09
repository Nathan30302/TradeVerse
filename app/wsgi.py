"""
WSGI entry point for production servers (Gunicorn).

Runs Alembic upgrades here (with a process lock) so the schema stays current even if
the platform start command omitted `flask db upgrade`.
"""

import logging
import os

try:
    import fcntl  # Unix only — Render/Linux always has this
except ImportError:  # pragma: no cover
    fcntl = None

_logger = logging.getLogger("tradeverse.wsgi")

from app import create_app  # noqa: E402

# Determine environment from FLASK_ENV or default to production
config_name = os.getenv("FLASK_ENV") or "production"


def _migrate_production_locked(flask_app) -> None:
    """Apply pending migrations exactly once-ish across worker processes."""

    skip = os.getenv("DISABLE_STARTUP_DB_UPGRADE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if skip or config_name != "production":
        return
    lock_path = os.getenv("TV_ALEMBIC_LOCK_PATH", "/tmp/tradeverse_alembic.lock")

    from flask_migrate import upgrade as alembic_upgrade

    fp = None
    try:
        fp = open(lock_path, "a+", encoding="utf-8")  # noqa: PTH123 — /tmp requires path str
        if fcntl:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)

        # upgrade() attaches to app's alembic config via Flask-Migrate
        try:
            with flask_app.app_context():
                alembic_upgrade()
        except Exception:
            # Don’t block boot if the DB can’t be migrated yet (legacy / locked DB).
            _logger.warning("Alembic upgrade skipped or failed — run `flask db upgrade` when ready", exc_info=True)
    finally:
        if fp is not None:
            try:
                if fcntl:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
            finally:
                fp.close()


# Create the Flask application after helpers are defined so imports stay ordered.
app = create_app(config_name)

try:
    _migrate_production_locked(app)
except Exception:
    _logger.warning("Startup migration hook failed (non-fatal); app will load without upgraded schema", exc_info=True)
