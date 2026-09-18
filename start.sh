#!/usr/bin/env bash
# Boots the scheduler and the terminal together. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> backend  http://127.0.0.1:8000"
./backend/run.sh &

echo "==> frontend http://127.0.0.1:5173"
(cd frontend && npm install --silent && npm run dev) &

wait
