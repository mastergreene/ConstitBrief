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
if ! .venv/bin/python -c "from backend.app import db; db.init_db(); import sqlite3,sys; sys.exit(0 if sqlite3.connect(str(__import__('backend.app.config',fromlist=['settings']).settings.db_path)).execute('select count(*) from users').fetchone()[0] else 1)"; then
  echo "No users yet. Create one with:  .venv/bin/python -m backend.app.manage add-user <username> \"<Name>\" --role admin"
fi
exec .venv/bin/python -m backend.app.main
