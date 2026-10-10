"""SQLite storage: standard-response templates, search cache and recent case drafts."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .config import SEED_FILE, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,
    tags          TEXT NOT NULL DEFAULT '[]',
    summary       TEXT NOT NULL DEFAULT '',
    sms           TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL DEFAULT '',
    source_urls   TEXT NOT NULL DEFAULT '[]',
    needs_review  INTEGER NOT NULL DEFAULT 0,
    last_reviewed TEXT,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category);

CREATE TABLE IF NOT EXISTS search_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   TEXT UNIQUE,
    category    TEXT NOT NULL DEFAULT 'general',
    mode        TEXT NOT NULL DEFAULT 'resolve',
    label       TEXT NOT NULL DEFAULT '',
    data        TEXT NOT NULL DEFAULT '{}',
    notes       TEXT NOT NULL DEFAULT '',
    draft       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at);
"""

_init_lock = threading.Lock()
_initialised: set[Path] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    path = settings.db_path
    init_db(path)
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    path = path or settings.db_path
    if path in _initialised:
        return
    with _init_lock:
        if path in _initialised:
            return
        conn = _connect(path)
        try:
            conn.executescript(SCHEMA)
            count = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
            if count == 0:
                _seed_templates(conn)
            conn.commit()
        finally:
            conn.close()
        _initialised.add(path)


def _seed_templates(conn: sqlite3.Connection, seed_file: Path = SEED_FILE) -> int:
    items = json.loads(seed_file.read_text(encoding="utf-8"))
    ts = now_iso()
    for t in items:
        conn.execute(
            """INSERT OR IGNORE INTO templates
               (slug, title, category, tags, summary, sms, body, source_urls,
                needs_review, last_reviewed, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                t["slug"],
                t["title"],
                t["category"],
                json.dumps(t.get("tags", [])),
                t.get("summary", ""),
                t.get("sms", ""),
                t.get("body", ""),
                json.dumps(t.get("source_urls", [])),
                1 if t.get("needs_review", True) else 0,
                t.get("last_reviewed"),
                ts,
            ),
        )
    return len(items)


def reseed_missing() -> int:
    """Insert any seed templates whose slug isn't present (never overwrites edits)."""
    with get_conn() as conn:
        before = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
        _seed_templates(conn)
        after = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    return after - before


def purge_old_cases() -> int:
    if settings.case_retention_days <= 0:
        return 0
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=settings.case_retention_days)
    ).replace(microsecond=0).isoformat()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM cases WHERE updated_at < ?", (cutoff,))
        return cur.rowcount
