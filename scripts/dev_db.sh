#!/bin/bash
# Local PostgreSQL 16 without Docker (for development on macOS).
#   scripts/dev_db.sh         start (first run installs it into .pgvenv and creates .pgdata)
#   scripts/dev_db.sh stop    stop
# Matches .env.example: localhost:5432, user sdu, databases sdu_score and sdu_score_test.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=5432
DATA="$PWD/.pgdata"

if [ ! -x .pgvenv/bin/python ]; then
  echo "Installing local PostgreSQL (one time)..."
  /usr/bin/python3 -m venv .pgvenv
  .pgvenv/bin/pip install -q --upgrade pip >/dev/null
  .pgvenv/bin/pip install -q pgserver
fi
BIN=$(.pgvenv/bin/python -c "import os, pgserver; print(os.path.join(os.path.dirname(pgserver.__file__), 'pginstall', 'bin'))")

if [ "${1:-start}" = "stop" ]; then
  "$BIN/pg_ctl" -D "$DATA" stop -m fast
  exit 0
fi

if [ ! -f "$DATA/PG_VERSION" ]; then
  "$BIN/initdb" -D "$DATA" -U sdu --auth=trust -E UTF8 >/dev/null
fi

if "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
  echo "PostgreSQL is already running."
else
  "$BIN/pg_ctl" -D "$DATA" -l "$DATA/server.log" -w start \
    -o "-p $PORT -c listen_addresses=localhost -k /tmp" >/dev/null
  echo "PostgreSQL started on localhost:$PORT."
fi

for db in sdu_score sdu_score_test; do
  if ! "$BIN/psql" -h localhost -p $PORT -U sdu -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    "$BIN/createdb" -h localhost -p $PORT -U sdu "$db"
    echo "Created database $db."
  fi
done
