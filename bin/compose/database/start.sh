#!/bin/bash
set -euo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

/usr/local/bin/docker-entrypoint.sh postgres &
POSTGRES_PID=$!

echo "Waiting for Postgres to be ready..."
MAX_WAIT=60
WAITED=0
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
  sleep 1
  WAITED=$((WAITED+1))
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "Postgres readiness timed out after ${MAX_WAIT}s" >&2
    kill -TERM "$POSTGRES_PID" || true
    wait "$POSTGRES_PID" || true
    exit 1
  fi
done

echo "Applying schema (idempotent)..."
psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /initdb.d/schema.sql

wait "$POSTGRES_PID"

