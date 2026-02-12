#!/bin/bash
set -e

echo "=== AI Summary — Web Starting ==="

# Fix postgres:// → postgresql:// if needed (Supabase/Railway compat)
if [[ "$DATABASE_URL" == postgres://* ]]; then
  export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql:\/\/}"
fi

# Start web server
echo "Starting web server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
