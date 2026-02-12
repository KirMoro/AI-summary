#!/bin/bash
set -e

echo "=== AI Summary — Worker Starting ==="

# Fix postgres:// → postgresql:// if needed
if [[ "$DATABASE_URL" == postgres://* ]]; then
  export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql:\/\/}"
fi

echo "Starting RQ worker on queue ${RQ_QUEUE_NAME:-default}..."
exec rq worker --url "$REDIS_URL" "${RQ_QUEUE_NAME:-default}"
