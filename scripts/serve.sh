#!/usr/bin/env bash
set -euo pipefail
# Manage THIS project's dev server (uvicorn app.main:app), in the background.
#
# The server keeps running after the terminal that started it closes. Stop it
# with `chess-coach stop`.
#
# Usage: scripts/serve.sh {start|stop|restart|status}
#        PORT=8123 scripts/serve.sh start                 # override the port
#        PIDFILE=.alt.pid LOGFILE=.alt.log … start        # a second instance

# Resolve the repo from this script's own location and work from there. This has
# to happen unconditionally: bin/chess-coach may be invoked through a symlink in
# ~/.local/bin from any directory, so the caller's working directory says
# nothing about where the checkout is.
REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PORT="${PORT:-8001}"
APP="app.main:app"
PY="${PY:-$REPO/.venv/bin/python}"
PIDFILE="${PIDFILE:-$REPO/.server.pid}"
LOGFILE="${LOGFILE:-$REPO/.server.log}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-30}"   # seconds to wait for the server to answer
STOP_TIMEOUT="${STOP_TIMEOUT:-5}"        # seconds to wait for a clean exit

# How we identify our own server, and why it is the arguments rather than the
# interpreter path: on macOS a virtualenv's `python` is a symlink into the
# framework build, and the framework rewrites argv[0] to its own
# .../Python.app/Contents/MacOS/Python path. The venv path — and so the checkout
# — never appears in `ps` output at all. Anchoring on it would mean the
# comparison never matches and every check reports "not running".
#
# Identity is therefore the argument tail, which this script controls entirely.
# Nothing else runs uvicorn on this app and this port, so a recycled PID or an
# unrelated process can never be taken for our server — which is what makes
# `stop` safe. The launch line below is deliberately byte-identical to the one
# this script has always used, so a server started by the previous version of
# this script is still found and stopped by this one.
EXPECTED_ARGS="-m uvicorn $APP --port $PORT"

url() { printf 'http://127.0.0.1:%s' "$PORT"; }

# A PID's full command line, or nothing.
# `-ww` is load-bearing: macOS ps truncates output to the terminal width by
# default, and this launch line runs past 80 characters once the interpreter
# path is included. Without it the comparison below would silently never match.
cmdline_of() { ps -ww -o command= -p "$1" 2>/dev/null || true; }

# True when the PID is alive AND is this app's server on this port. The command
# line must *end* with the expected arguments, so `--port 8001` cannot match a
# server on `--port 80010`. If ps is unavailable (restricted sandboxes), fall
# back to trusting liveness alone.
pid_is_ours() {
  local pid="$1" cmdline
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  cmdline="$(cmdline_of "$pid")"
  if [ -z "$cmdline" ]; then return 0; fi
  case "$cmdline" in
    *" $EXPECTED_ARGS") return 0 ;;
    *) return 1 ;;
  esac
}

# Echo a live PID for our server, or nothing. Validated PID file first; then a
# scan, so a server started outside this script is still found by status/stop.
server_pid() {
  local pid
  if [ -f "$PIDFILE" ]; then
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if pid_is_ours "$pid"; then echo "$pid"; return 0; fi
    rm -f "$PIDFILE"      # stale, recycled, or a different port — discard
  fi
  for pid in $(pgrep -f "uvicorn $APP" 2>/dev/null || true); do
    if pid_is_ours "$pid"; then echo "$pid"; return 0; fi
  done
}

# This app's server on some *other* port — reported so "why am I looking at
# stale data" has an obvious answer, never killed, and never a reason to refuse
# to start. The `-m uvicorn` prefix is this project's launch shape and keeps
# sibling projects that also serve an `app.main:app` out of the results.
other_instances() {
  local pid cmdline
  for pid in $(pgrep -f "uvicorn $APP" 2>/dev/null || true); do
    cmdline="$(cmdline_of "$pid")"
    case "$cmdline" in
      *" -m uvicorn $APP --port "*)
        if ! pid_is_ours "$pid"; then printf '%s  %s\n' "$pid" "$cmdline"; fi
        ;;
    esac
  done
}

# `curl` and `wget` are denied by this repo's Claude sandbox, so readiness is
# probed with the standard library. There is no /health route, so a 200 on the
# app root is the readiness signal: it proves uvicorn bound the port and the
# application finished starting. That takes several seconds here, because
# startup initialises the engine seam — which is why the old fixed `sleep 1`
# reported success long before the server could answer.
health_ok() {
  "$PY" - "$PORT" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/", timeout=2) as response:
    sys.exit(0 if response.status == 200 else 1)
PY
}

fail_with_log() {
  echo "$1" >&2
  if [ -f "$LOGFILE" ]; then
    echo "last lines of ${LOGFILE#"$REPO"/}:" >&2
    tail -n 15 "$LOGFILE" >&2 || true
  fi
  exit 1
}

start() {
  if [ ! -x "$PY" ]; then
    echo "missing venv interpreter ($PY)" >&2
    echo "run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi

  local pid; pid="$(server_pid)"
  if [ -n "$pid" ]; then
    echo "already running (pid $pid, $(url))"
    return 0
  fi

  local others; others="$(other_instances)"
  if [ -n "$others" ]; then
    echo "note: another chess-coach server is already running elsewhere:"
    printf '%s\n' "$others" | sed 's/^/  /'
  fi

  # Roll the previous log rather than appending to it forever.
  if [ -f "$LOGFILE" ]; then mv -f "$LOGFILE" "$LOGFILE.1"; fi

  STOCKFISH_PATH="${STOCKFISH_PATH:-$(command -v stockfish || true)}" \
    nohup "$PY" -m uvicorn "$APP" --port "$PORT" >"$LOGFILE" 2>&1 &
  pid=$!
  echo "$pid" >"$PIDFILE"

  printf 'waiting for %s' "$(url)"
  local ticks=$(( HEALTH_TIMEOUT * 2 ))
  while [ "$ticks" -gt 0 ]; do
    if health_ok; then
      echo " — up"
      echo "started (pid $pid, $(url)) — logs: ${LOGFILE#"$REPO"/}"
      echo "keeps running after this terminal closes; stop with: chess-coach stop"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PIDFILE"
      echo ""
      fail_with_log "server exited during startup"
    fi
    printf '.'
    sleep 0.5
    ticks=$(( ticks - 1 ))
  done

  echo ""
  fail_with_log "server did not answer $(url) within ${HEALTH_TIMEOUT}s (pid $pid still up)"
}

# TERM children before the parent so nothing orphans while still holding the
# port, then wait for real exit — otherwise `restart` can launch a new server
# before the old one has released the socket. Escalate to KILL if it hangs.
stop_pid() {
  local pid="$1" ticks=$(( STOP_TIMEOUT * 4 ))
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  while [ "$ticks" -gt 0 ] && kill -0 "$pid" 2>/dev/null; do
    sleep 0.25
    ticks=$(( ticks - 1 ))
  done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -KILL -P "$pid" 2>/dev/null || true
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop() {
  local pid; pid="$(server_pid)"
  if [ -z "$pid" ]; then
    rm -f "$PIDFILE"
    echo "not running"
    return 0
  fi
  stop_pid "$pid"
  rm -f "$PIDFILE"
  echo "stopped (pid $pid)"
}

status() {
  local pid; pid="$(server_pid)"
  if [ -z "$pid" ]; then
    echo "not running"
    local others; others="$(other_instances)"
    if [ -n "$others" ]; then
      echo "note: another chess-coach server is up elsewhere:"
      printf '%s\n' "$others" | sed 's/^/  /'
    fi
    return 0
  fi
  echo "running (pid $pid, $(url))"
  if health_ok; then
    echo "  health: 200"
  else
    echo "  health: not answering — check ${LOGFILE#"$REPO"/}"
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)  status ;;
  *) echo "usage: scripts/serve.sh {start|stop|restart|status}" >&2; exit 2 ;;
esac
