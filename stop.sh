#!/usr/bin/env bash
# Stop the API and web app started by ./start.sh.
set -euo pipefail

RUN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.run"

stop() {  # name
  local pidfile="$RUN/$1.pid" pid
  if [[ ! -f "$pidfile" ]]; then echo "$1: not running"; return; fi
  pid="$(cat "$pidfile")"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$1: not running (removing stale pid file)"
    rm -f "$pidfile"
    return
  fi
  kill -TERM "$pid"
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "$1: did not stop in 10s, forcing"
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
  echo "$1: stopped"
}

stop web
stop api
