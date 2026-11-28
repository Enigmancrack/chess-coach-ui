#!/usr/bin/env bash
# Start the coach in THIS terminal. Ctrl+C stops it; nothing is left behind.
set -euo pipefail
cd "$(dirname "$0")"
port="${1:-8770}"
if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$port/"; then
  echo "port $port is already taken — stop that first (Ctrl+C in its terminal)"
  exit 1
fi
echo "coach on http://127.0.0.1:$port  (Ctrl+C to stop)"
exec python3 server.py --port "$port"
