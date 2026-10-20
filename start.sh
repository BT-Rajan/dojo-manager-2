#!/usr/bin/env bash
# Start Dojo Manager on one port (default 8090): the API process also serves the web app.
#
#   ./start.sh
#
# Builds the web app when its sources changed, applies database migrations, then runs the
# app as "dojo" under pm2 (and saves the pm2 process list). Without pm2 it runs in the
# background with logs in .run/. Port and address: DOJO_PORT / DOJO_HOST in backend/.env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
mkdir -p "$RUN"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
[[ -x "$VENV/bin/uvicorn" && -d "$FRONTEND/node_modules" && -f "$BACKEND/.env" ]] \
  || die "not set up yet; run ./runonce.sh first"

# A setting exactly as the app sees it (backend/.env plus DOJO_* overrides).
setting() {
  (cd "$BACKEND" && "$VENV/bin/python" -c \
    "import sys; from app.core.config import get_settings; print(getattr(get_settings(), sys.argv[1]))" "$1")
}
PORT="$(setting port)"
HOST="$(setting host)"
CHECK_HOST="$HOST"
[[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]] && CHECK_HOST="127.0.0.1"

port_busy() { (exec 3<>"/dev/tcp/$CHECK_HOST/$PORT") 2>/dev/null; }
alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

stop_pidfile() {  # pidfile label
  alive "$1" || { rm -f "$1"; return 0; }
  local pid; pid="$(cat "$1")"
  kill -TERM "$pid"
  for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$1"
  echo "Stopped $2 (pid $pid)"
}

# Earlier versions ran a separate API (:8000) and Vite dev server (:5173).
stop_pidfile "$RUN/api.pid" "old API process"
stop_pidfile "$RUN/web.pid" "old web dev server"

# ---------------------------------------------------------------- web app build
DIST_INDEX="$FRONTEND/dist/index.html"
needs_build() {
  [[ -f "$DIST_INDEX" ]] || return 0
  [[ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/package-lock.json" \
    "$FRONTEND/vite.config.ts" "$FRONTEND/tailwind.config.ts" -newer "$DIST_INDEX" -print -quit)" ]]
}
if needs_build; then
  echo "Building the web app"
  (cd "$FRONTEND" && npm run build >"$RUN/build.log" 2>&1) \
    || { tail -n 30 "$RUN/build.log" >&2; die "web app build failed (full log: .run/build.log)"; }
else
  echo "Web app is up to date"
fi

# ---------------------------------------------------------------- database
echo "Applying any new database migrations"
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head >"$RUN/migrate.log" 2>&1) \
  || { tail -n 20 "$RUN/migrate.log" >&2; die "migrations failed (full log: .run/migrate.log)"; }

# ---------------------------------------------------------------- run
wait_healthy() {
  for _ in $(seq 1 30); do
    curl -fsS "http://$CHECK_HOST:$PORT/api/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

if command -v pm2 >/dev/null; then
  export DOJO_HOST="$HOST" DOJO_PORT="$PORT"
  if pm2 describe dojo >/dev/null 2>&1; then
    echo "Restarting pm2 app 'dojo' on port $PORT"
    pm2 reload "$ROOT/ecosystem.config.cjs" --only dojo --update-env >/dev/null
  else
    port_busy && die "port $PORT is already in use by another program"
    echo "Starting pm2 app 'dojo' on port $PORT"
    pm2 start "$ROOT/ecosystem.config.cjs" --only dojo >/dev/null
  fi
  pm2 save >/dev/null
  wait_healthy || { pm2 logs dojo --lines 30 --nostream >&2 || true; die "dojo did not come up"; }
  RUNNER="pm2 (logs: pm2 logs dojo)"
else
  if alive "$RUN/dojo.pid"; then
    echo "Already running (pid $(cat "$RUN/dojo.pid"))"
  else
    port_busy && die "port $PORT is already in use by another program"
    echo "Starting on port $PORT (pm2 not found; running in the background)"
    # `exec` makes the background job the server itself, so $! is its pid.
    (cd "$BACKEND" && exec nohup "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" \
      --no-server-header --timeout-graceful-shutdown 10) >"$RUN/dojo.log" 2>&1 &
    echo $! >"$RUN/dojo.pid"
  fi
  wait_healthy || { tail -n 30 "$RUN/dojo.log" >&2; die "dojo did not come up"; }
  RUNNER="background process (log: .run/dojo.log)"
fi

ADDRESS="$CHECK_HOST"
if [[ "$CHECK_HOST" == "127.0.0.1" && "$HOST" != "127.0.0.1" ]]; then
  ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
  ADDRESS="${ADDRESS:-localhost}"
fi
echo
echo "Dojo Manager is running: http://$ADDRESS:$PORT"
echo "Runs as: $RUNNER   Stop: ./stop.sh"
if [[ "$(setting cookie_secure)" == "True" ]]; then
  echo
  echo "Note: DOJO_COOKIE_SECURE is on, so signing in only works over HTTPS. To use"
  echo "      plain http://$ADDRESS:$PORT, set DOJO_COOKIE_SECURE=false in backend/.env"
  echo "      and run ./start.sh again."
fi
