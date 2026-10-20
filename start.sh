#!/usr/bin/env bash
# Start the API and the web app in the background.
#
#   ./start.sh            # API on :8000, web on :5173 (override with API_PORT / WEB_PORT)
#
# Logs and process ids go to .run/. Stop with ./stop.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
VENV="$ROOT/backend/.venv"
mkdir -p "$RUN"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
[[ -x "$VENV/bin/uvicorn" && -d "$ROOT/frontend/node_modules" && -f "$ROOT/backend/.env" ]] \
  || die "not set up yet; run ./runonce.sh first"

running() { [[ -f "$RUN/$1.pid" ]] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

wait_for() {  # name url
  for _ in $(seq 1 30); do
    if curl -fsS "$2" >/dev/null 2>&1; then return 0; fi
    running "$1" || break
    sleep 1
  done
  echo "  $1 did not come up; last log lines:" >&2
  tail -n 20 "$RUN/$1.log" >&2
  return 1
}

start_api() {
  if running api; then echo "API already running (pid $(cat "$RUN/api.pid"))"; return; fi
  port_busy "$API_PORT" && die "port $API_PORT is in use by another program"
  echo "Applying any new database migrations"
  (cd "$ROOT/backend" && "$VENV/bin/alembic" upgrade head >"$RUN/migrate.log" 2>&1) \
    || { tail -n 20 "$RUN/migrate.log" >&2; die "migrations failed"; }
  echo "Starting API on http://127.0.0.1:$API_PORT"
  # `exec` replaces the background subshell with the server, so $! is the server's pid.
  (cd "$ROOT/backend" && exec nohup "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 \
    --port "$API_PORT") >"$RUN/api.log" 2>&1 &
  echo $! >"$RUN/api.pid"
  wait_for api "http://127.0.0.1:$API_PORT/api/health"
}

start_web() {
  if running web; then echo "Web app already running (pid $(cat "$RUN/web.pid"))"; return; fi
  port_busy "$WEB_PORT" && die "port $WEB_PORT is in use by another program"
  echo "Starting web app on http://localhost:$WEB_PORT"
  (cd "$ROOT/frontend" && VITE_API_TARGET="http://127.0.0.1:$API_PORT" exec nohup \
    node node_modules/vite/bin/vite.js --port "$WEB_PORT" --strictPort) >"$RUN/web.log" 2>&1 &
  echo $! >"$RUN/web.pid"
  wait_for web "http://localhost:$WEB_PORT/"
}

start_api
start_web
echo
echo "Dojo Manager is running: http://localhost:$WEB_PORT"
echo "Logs: .run/api.log, .run/web.log   Stop: ./stop.sh"
