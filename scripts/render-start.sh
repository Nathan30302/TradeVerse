#!/usr/bin/env bash
# Apply Alembic migrations before workers start (DATABASE_URL required at runtime on Render).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

export FLASK_APP="${FLASK_APP:-app.wsgi:app}"
echo "[render-start] $(date -u +%Y-%m-%dT%H:%M:%SZ) flask db upgrade (non-fatal if DB is behind)"
python -m flask db upgrade || echo "[render-start] flask db upgrade exited non-zero — continuing boot"
# If multiple Alembic heads exist, try upgrading all of them.
python -m flask db upgrade heads || echo "[render-start] flask db upgrade heads exited non-zero — continuing boot"

# Prefer configured persistent disk; fall back if /var/data is not mounted/writable.
# (Dashboard-created Render services often set TRADEVERSE_DATA_DIR without attaching a disk.)
_can_write_dir() {
  local d="$1"
  mkdir -p "$d" 2>/dev/null || return 1
  local probe="${d}/.tv_write_probe_$$"
  if ! ( : >"$probe" ) 2>/dev/null; then
    return 1
  fi
  rm -f "$probe" 2>/dev/null || true
  return 0
}

PREFERRED_DATA_DIR="${TRADEVERSE_DATA_DIR:-${PERSISTENT_DISK_PATH:-/var/data}}"
FALLBACK_DATA_DIR="$(pwd)/app/static"
DATA_DIR="$PREFERRED_DATA_DIR"

if ! _can_write_dir "$DATA_DIR"; then
  echo "[render-start] WARN: ${PREFERRED_DATA_DIR} is not writable (no Render disk mounted?)."
  echo "[render-start] Falling back to ${FALLBACK_DATA_DIR} — uploads/OHLC cache will be ephemeral until you attach a disk at /var/data."
  DATA_DIR="$FALLBACK_DATA_DIR"
  if ! _can_write_dir "$DATA_DIR"; then
    echo "[render-start] WARN: fallback also failed; trying /tmp/tradeverse_data"
    DATA_DIR="/tmp/tradeverse_data"
    _can_write_dir "$DATA_DIR" || echo "[render-start] WARN: could not create upload dirs"
  fi
fi

export TRADEVERSE_DATA_DIR="$DATA_DIR"
echo "[render-start] TRADEVERSE_DATA_DIR=${TRADEVERSE_DATA_DIR}"

mkdir -p "${DATA_DIR}/uploads/avatars" \
         "${DATA_DIR}/uploads/trade_screenshots" \
         "${DATA_DIR}/uploads/replay" \
         "${DATA_DIR}/uploads/playbook" \
         "${DATA_DIR}/uploads/ohlc_cache" 2>/dev/null || true

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
