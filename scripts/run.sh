#!/usr/bin/env bash
# Create a virtualenv (first run), install deps, and start the app.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
fi
.venv/bin/pip install --quiet -r requirements.txt
[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m backend.app.main
