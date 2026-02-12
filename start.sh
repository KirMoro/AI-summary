#!/bin/bash
set -e

ROLE="${APP_ROLE:-web}"
echo "=== AI Summary — Starting (${ROLE}) ==="

# Fix postgres:// → postgresql:// if needed (Supabase/Railway compat)
if [[ "$DATABASE_URL" == postgres://* ]]; then
  export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql:\/\/}"
fi

if [[ "$ROLE" == "worker" ]]; then
  echo "Starting RQ worker on queue ${RQ_QUEUE_NAME:-default}..."
  exec rq worker --url "$REDIS_URL" "${RQ_QUEUE_NAME:-default}"
fi

echo "Starting web server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
