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
    reviewed_by   TEXT,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category);

CREATE TABLE IF NOT EXISTS search_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'staff',   -- staff | mp | admin
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

-- Working draft of one conversation. Holds notes + staff record until it expires or the
-- officer clears it. This is draft recovery, not a case-management system of record.
CREATE TABLE IF NOT EXISTS interactions (
    id          TEXT PRIMARY KEY,
    ref         TEXT NOT NULL UNIQUE,
    officer_id  INTEGER NOT NULL REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'open',      -- open | cleared
    version     INTEGER NOT NULL DEFAULT 0,
    notes       TEXT NOT NULL DEFAULT '',
    state       TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interactions_officer ON interactions(officer_id, updated_at);

-- Handoff audit trail. Deliberately holds no notes or field values.
CREATE TABLE IF NOT EXISTS handoffs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id  TEXT NOT NULL,
    ref             TEXT NOT NULL UNIQUE,
    type_id         TEXT NOT NULL,
    form_option     TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    status          TEXT NOT NULL,   -- prepared | opened | reported_submitted | confirmed | cancelled
    valid           INTEGER NOT NULL DEFAULT 0,
    payload_hash    TEXT NOT NULL DEFAULT '',
    approved_by     INTEGER REFERENCES users(id),
    prepared_at     TEXT NOT NULL,
    opened_at       TEXT,
    reported_at     TEXT,
    confirmed_at    TEXT,
    submission_id   TEXT,
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_handoffs_interaction ON handoffs(interaction_id);
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
            cols = {r[1] for r in conn.execute("PRAGMA table_info(templates)")}
            if "reviewed_by" not in cols:
                conn.execute("ALTER TABLE templates ADD COLUMN reviewed_by TEXT")
            # Category ids from the first prototype -> enquiry type ids.
            for old, new in (("general", "admin"), ("ato_nbn_dva", "ato"), ("flags_messages", "flag")):
                conn.execute("UPDATE templates SET category = ? WHERE category = ?", (new, old))
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


def purge_expired() -> int:
    """Delete expired interaction drafts and sessions. Handoff audit rows are kept."""
    ts = now_iso()
    with get_conn() as conn:
        n = conn.execute("DELETE FROM interactions WHERE expires_at < ?", (ts,)).rowcount
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (ts,))
        # Tables from the earlier prototype that stored case data in the clear.
        conn.execute("DROP TABLE IF EXISTS cases")
    return n


def expiry(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()
