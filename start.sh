#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r backend/requirements.txt
fi
if [ ! -f frontend/dist/index.html ]; then
  npm ci --prefix frontend
  npm run build --prefix frontend
fi
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
