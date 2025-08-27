#!/bin/bash
set -euo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

/usr/local/bin/docker-entrypoint.sh postgres &
POSTGRES_PID=$!

echo "Waiting for Postgres to be ready..."
until pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
  sleep 1
done

echo "Applying schema (idempotent)..."
psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /initdb.d/schema.sql || true

wait "$POSTGRES_PID"

