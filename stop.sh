#!/usr/bin/env bash
# Stop Dojo Manager (the pm2 app "dojo", or the background process without pm2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"

stopped=0
if command -v pm2 >/dev/null && pm2 describe dojo >/dev/null 2>&1; then
  pm2 stop dojo >/dev/null
  pm2 save >/dev/null  # so a reboot does not bring back an app stopped on purpose
  echo "dojo: stopped (pm2)"
  stopped=1
fi

stop_pidfile() {  # pidfile label
  [[ -f "$1" ]] || return 0
  local pid; pid="$(cat "$1")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid"
    for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
      echo "$2: did not stop in 10s, forcing"
      kill -KILL "$pid" 2>/dev/null || true
    fi
    echo "$2: stopped"
    stopped=1
  fi
  rm -f "$1"
}
stop_pidfile "$RUN/dojo.pid" "dojo"
# Processes from earlier versions (separate API on :8000 and web dev server on :5173).
stop_pidfile "$RUN/api.pid" "old API process"
stop_pidfile "$RUN/web.pid" "old web dev server"

(( stopped )) || echo "dojo: not running"
