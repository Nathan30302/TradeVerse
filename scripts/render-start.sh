#!/usr/bin/env bash
# Resolve disk + secrets first, then migrate, then Gunicorn.
# Railway first-deploys often have no Variables UI yet — persist generated
# SECRET_KEY / SQLite on the volume so production can boot.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

export FLASK_APP="${FLASK_APP:-app.wsgi:app}"

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

# Prefer configured persistent disk; fall back if /var/data is not mounted/writable.
# (Dashboard-created Render services often set TRADEVERSE_DATA_DIR without attaching a disk.)
PREFERRED_DATA_DIR="${TRADEVERSE_DATA_DIR:-${UPLOAD_ROOT:-${PERSISTENT_DISK_PATH:-/var/data}}}"
FALLBACK_DATA_DIR="$(pwd)/app/static"
DATA_DIR="$PREFERRED_DATA_DIR"

S3_NAME="${S3_BUCKET:-${AWS_S3_BUCKET:-${R2_BUCKET:-}}}"
if [[ -n "$S3_NAME" && -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "[render-start] Object storage configured (bucket=${S3_NAME}) — uploads persist across redeploys."
fi

if ! _can_write_dir "$DATA_DIR"; then
  echo "[render-start] WARN: ${PREFERRED_DATA_DIR} is not writable (no Render disk mounted?)."
  if [[ -z "$S3_NAME" || -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
    echo "[render-start] Falling back to ${FALLBACK_DATA_DIR} — uploads/OHLC cache will be EPHEMERAL until you either:"
    echo "[render-start]   (A) set S3_BUCKET + AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (+ S3_ENDPOINT_URL for R2), or"
    echo "[render-start]   (B) attach a persistent volume at /var/data (Render disk or Railway volume) and set TRADEVERSE_DATA_DIR=/var/data."
  else
    echo "[render-start] Local cache dir unavailable; S3/R2 will still hold durable uploads."
  fi
  DATA_DIR="$FALLBACK_DATA_DIR"
  if ! _can_write_dir "$DATA_DIR"; then
    echo "[render-start] WARN: fallback also failed; trying /tmp/tradeverse_data"
    DATA_DIR="/tmp/tradeverse_data"
    _can_write_dir "$DATA_DIR" || echo "[render-start] WARN: could not create upload dirs"
  fi
fi

export TRADEVERSE_DATA_DIR="$DATA_DIR"
echo "[render-start] TRADEVERSE_DATA_DIR=${TRADEVERSE_DATA_DIR}"

# Production create_app() refuses to boot without these. First Railway deploys
# often cannot set Variables yet — persist on the volume when possible.
if [[ -z "${SECRET_KEY:-}" ]]; then
  KEY_FILE="${DATA_DIR}/.secret_key"
  if [[ -s "$KEY_FILE" ]]; then
    SECRET_KEY="$(tr -d '\r\n' < "$KEY_FILE")"
    echo "[render-start] loaded SECRET_KEY from ${KEY_FILE}"
  else
    SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    if printf '%s\n' "$SECRET_KEY" > "$KEY_FILE" 2>/dev/null; then
      echo "[render-start] generated SECRET_KEY and saved ${KEY_FILE}"
    else
      echo "[render-start] WARN: could not persist SECRET_KEY to ${KEY_FILE} — sessions reset on redeploy"
    fi
  fi
  export SECRET_KEY
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="sqlite:///${DATA_DIR}/tradeverse.db"
  echo "[render-start] WARN: DATABASE_URL unset — using ${DATABASE_URL}"
  echo "[render-start] Attach Railway/Render Postgres and set DATABASE_URL for a real production DB."
fi

echo "[render-start] $(date -u +%Y-%m-%dT%H:%M:%SZ) flask db upgrade (non-fatal if DB is behind)"
python -m flask db upgrade || echo "[render-start] flask db upgrade exited non-zero — continuing boot"
# If multiple Alembic heads exist, try upgrading all of them.
python -m flask db upgrade heads || echo "[render-start] flask db upgrade heads exited non-zero — continuing boot"

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

# Railway hobby/trial RAM is tighter than typical Render instances.
if [[ -n "${RAILWAY_ENVIRONMENT:-}${RAILWAY_ENVIRONMENT_NAME:-}" ]]; then
  DEFAULT_WORKERS=2
else
  DEFAULT_WORKERS=4
fi
WORKERS="${WEB_CONCURRENCY:-$DEFAULT_WORKERS}"
echo "[render-start] starting gunicorn workers=${WORKERS} port=${PORT:-5000}"
exec gunicorn -w "$WORKERS" -b "0.0.0.0:${PORT:-5000}" app.wsgi:app
