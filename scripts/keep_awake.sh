#!/usr/bin/env bash
# scripts/keep_awake.sh
# Lightweight cross-platform keep-awake wrapper.
# On systemd systems this uses systemd-inhibit. On macOS it will try `caffeinate` if present.

set -euo pipefail

if command -v systemd-inhibit >/dev/null 2>&1; then
  echo "Using systemd-inhibit to block idle/sleep. Press Ctrl+C to stop."
  systemd-inhibit --what=idle --why="Keep trading bot awake for testing" bash -c 'while true; do sleep 3600; done'
  exit 0
fi

if command -v caffeinate >/dev/null 2>&1; then
  echo "Using caffeinate (macOS). Press Ctrl+C to stop."
  caffeinate -dims
  exit 0
fi

# Fallback: busy loop with sleeps (not ideal but works)
echo "No systemd-inhibit or caffeinate found; running fallback busy loop. Press Ctrl+C to stop."
while true; do sleep 3600; done
