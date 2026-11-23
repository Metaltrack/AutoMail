"""SQLite storage. One short-lived connection per operation keeps it thread-safe."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "automail.db"))
ATTACHMENT_DIR = Path(os.getenv("ATTACHMENT_DIR", BASE_DIR / "data" / "attachments"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'sender')),
    created_at    INTEGER NOT NULL,
    email         TEXT COLLATE NOCASE,            -- NULL for accounts an admin created by hand
    email_verified INTEGER NOT NULL DEFAULT 1     -- self-signups start at 0 until the mailed link is used
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose    TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,
    prefix       TEXT NOT NULL,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   INTEGER NOT NULL,
    last_used_at INTEGER,
    revoked      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contacts (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    extra      TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS groups (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS contact_groups (
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (contact_id, group_id)
);
CREATE TABLE IF NOT EXISTS attachments (
    id           INTEGER PRIMARY KEY,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size         INTEGER NOT NULL,
    path         TEXT NOT NULL,
    uploaded_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY,
    created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    api_key_id     INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    source         TEXT NOT NULL,             -- ui | api | webhook
    subject        TEXT NOT NULL,
    body           TEXT NOT NULL,
    html           INTEGER NOT NULL DEFAULT 0,
    reply_to       TEXT,
    recipients     TEXT NOT NULL,             -- JSON [{email, vars}]
    attachment_ids TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL,             -- scheduled | sending | done | partial | failed | cancelled
    scheduled_at   INTEGER NOT NULL,
    repeat         TEXT NOT NULL DEFAULT 'none',  -- none | daily | weekly
    parent_id      INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    created_at     INTEGER NOT NULL,
    finished_at    INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(status, scheduled_at);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    vars            TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed | cancelled
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    next_attempt_at INTEGER NOT NULL,
    sent_at         INTEGER
);
CREATE INDEX IF NOT EXISTS messages_pending ON messages(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS messages_job ON messages(job_id);
CREATE INDEX IF NOT EXISTS messages_sent ON messages(sent_at);
"""


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx():
    """Yields a connection inside a transaction; commits on success."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    with tx() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn):
    """Brings a database created by an older version up to date."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT COLLATE NOCASE")
    if "email_verified" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(email) WHERE email IS NOT NULL")


def rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]


def loads(text, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
