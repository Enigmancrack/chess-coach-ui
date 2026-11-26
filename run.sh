#!/usr/bin/env bash
# Start the coach in the background so it survives the terminal.
set -euo pipefail
cd "$(dirname "$0")"
port="${1:-8770}"
if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$port/"; then
  echo "already up on http://127.0.0.1:$port"
  exit 0
fi
setsid nohup python3 server.py --port "$port" >/tmp/opencode/coach-"$port".log 2>&1 < /dev/null &
sleep 3
curl -s -o /dev/null -w "coach on http://127.0.0.1:$port -> %{http_code}\n" "http://127.0.0.1:$port/"
