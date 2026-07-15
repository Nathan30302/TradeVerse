"""
WSGI entry point for production servers (Gunicorn).

Runs Alembic upgrades here (with a process lock) so the schema stays current even if
the platform start command omitted `flask db upgrade`. Then applies schema_compat
ensures for columns/tables Alembic may have skipped.
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

        try:
            with flask_app.app_context():
                from app import schema_compat

                # If alembic_version is empty/stuck on early branches while users exists,
                # stamp forward so we stop replaying initial schema every boot.
                schema_compat.repair_alembic_version(flask_app)
                try:
                    alembic_upgrade()
                except Exception:
                    _logger.warning(
                        "Alembic upgrade skipped or failed — applying schema_compat ensures",
                        exc_info=True,
                    )
                # Always ensure critical columns/tables exist (raw SQL, idempotent).
                schema_compat.ensure_lagging_schema(flask_app)
        except Exception:
            _logger.warning(
                "Alembic upgrade skipped or failed — run `flask db upgrade` when ready",
                exc_info=True,
            )
            try:
                with flask_app.app_context():
                    from app import schema_compat

                    schema_compat.ensure_lagging_schema(flask_app)
            except Exception:
                _logger.warning("schema_compat ensure after migrate failure also failed", exc_info=True)
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
    _logger.warning(
        "Startup migration hook failed (non-fatal); app will load without upgraded schema",
        exc_info=True,
    )
    try:
        with app.app_context():
            from app import schema_compat

            schema_compat.ensure_lagging_schema(app)
    except Exception:
        _logger.warning("Post-boot schema_compat ensure failed", exc_info=True)
