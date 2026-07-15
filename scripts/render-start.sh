#!/usr/bin/env bash
# Apply Alembic migrations before workers start (DATABASE_URL required at runtime on Render).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

export FLASK_APP="${FLASK_APP:-app.wsgi:app}"
echo "[render-start] $(date -u +%Y-%m-%dT%H:%M:%SZ) flask db upgrade (non-fatal if DB is behind)"
python -m flask db upgrade || echo "[render-start] flask db upgrade exited non-zero — continuing boot"

# Ensure durable upload dirs exist on the persistent disk
DATA_DIR="${TRADEVERSE_DATA_DIR:-/var/data}"
mkdir -p "${DATA_DIR}/uploads/avatars" \
         "${DATA_DIR}/uploads/trade_screenshots" \
         "${DATA_DIR}/uploads/replay" || true

# One-time Pro Plus promo grant for existing users (marker file on persistent disk)
if [[ "${TV_GRANT_PROMO_ON_START:-0}" =~ ^(1|true|yes|on)$ ]]; then
  MARKER="${DATA_DIR}/.promo_granted_60d_v1"
  if [[ ! -f "$MARKER" ]]; then
    echo "[render-start] granting 60-day Pro Plus trial to existing users"
    if python -m flask grant-promo-trial --days "${TV_ALL_USERS_PROPLUS_TRIAL_DAYS:-60}" --all-users; then
      touch "$MARKER" || true
      echo "[render-start] promo grant complete (marker: $MARKER)"
    else
      echo "[render-start] promo grant failed — continuing boot"
    fi
  else
    echo "[render-start] promo already granted (found $MARKER)"
  fi
fi

echo "[render-start] starting gunicorn"
exec gunicorn -w 4 -b "0.0.0.0:${PORT:-5000}" app.wsgi:app
