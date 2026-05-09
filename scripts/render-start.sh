#!/usr/bin/env bash
# Apply Alembic migrations before workers start (DATABASE_URL required at runtime on Render).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

export FLASK_APP="${FLASK_APP:-app.wsgi:app}"
echo "[render-start] $(date -u +%Y-%m-%dT%H:%M:%SZ) flask db upgrade (non-fatal if DB is behind)"
python -m flask db upgrade || echo "[render-start] flask db upgrade exited non-zero — continuing boot"
echo "[render-start] starting gunicorn"

exec gunicorn -w 4 -b "0.0.0.0:${PORT:-5000}" app.wsgi:app
