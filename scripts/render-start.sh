#!/usr/bin/env bash
# Apply Alembic migrations before workers start (DATABASE_URL required at runtime on Render).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

export FLASK_APP="${FLASK_APP:-app.wsgi:app}"
python -m flask db upgrade

exec gunicorn -w 4 -b "0.0.0.0:${PORT:-5000}" app.wsgi:app
