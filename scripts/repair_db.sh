#!/bin/bash
# Restart the Exasol Personal VM from Terminal.app.
#
# Why Terminal.app: on macOS Sequoia+ the IDE's process tree is silently denied
# Local Network access, so a launcher daemon started from here cannot reach the
# guest at 192.168.64.x ("no route to host"). A daemon started from Terminal.app
# inherits Terminal's permission and works. The guest currently has no database
# running (console stops at the Alpine login prompt), so killing the wedged
# daemon loses nothing; `start` reuses vm/disk.img and vm/data.img, so WARDQ
# survives.

set -u

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEPLOY="$HOME/.exasol/personal/deployments/default"
RUNTIME="$DEPLOY/local/runtime"
LOG="$HOME/exasol/.db_repair.log"

: >"$LOG"
run() {
  # Unpiped with </dev/null: piping makes the launcher look like it hangs.
  "$@" </dev/null >>"$LOG" 2>&1
}

echo "=== $(date) repairing local Exasol ==="

PID="$(cat "$RUNTIME/vm.pid" 2>/dev/null || true)"
if [ -n "${PID:-}" ] && ps -p "$PID" >/dev/null 2>&1; then
  echo "killing wedged launcher daemon $PID"
  kill -9 "$PID"
  rm -f "$RUNTIME/vm-state-degraded.json"
  sleep 5
else
  echo "no launcher daemon running (pid ${PID:-unknown})"
fi

pgrep -fl "launcher __daemon__" >>"$LOG" 2>&1 || echo "launcher gone" >>"$LOG"

echo "starting deployment (vm 2 vCPU / 6144 MB, data.img preserved)"
if run exasol start --auto-approve; then
  echo "start: OK"
else
  echo "start: FAILED — see log tail below"
fi

run exasol status
tail -n 25 "$LOG"
echo "=== $(date) done ==="
