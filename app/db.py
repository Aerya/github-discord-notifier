import os
import sqlite3
from flask import current_app, g

SCHEMA = '''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL UNIQUE,
    private INTEGER NOT NULL DEFAULT 0,
    owner_login TEXT NOT NULL,
    html_url TEXT,
    selected INTEGER NOT NULL DEFAULT 0,
    issues_enabled INTEGER NOT NULL DEFAULT 1,
    prs_enabled INTEGER NOT NULL DEFAULT 1,
    actions_enabled INTEGER NOT NULL DEFAULT 0,
    forks_enabled INTEGER NOT NULL DEFAULT 0,
    stars_enabled INTEGER NOT NULL DEFAULT 0,
    ignore_own_prs INTEGER NOT NULL DEFAULT 1,
    action_success INTEGER NOT NULL DEFAULT 0,
    action_failure INTEGER NOT NULL DEFAULT 1,
    action_cancelled INTEGER NOT NULL DEFAULT 0,
    last_sync_at TEXT
);
CREATE TABLE IF NOT EXISTS discord_webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url_encrypted TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS repository_webhooks (
    repository_id INTEGER NOT NULL,
    webhook_id INTEGER NOT NULL,
    PRIMARY KEY(repository_id, webhook_id),
    FOREIGN KEY(repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(webhook_id) REFERENCES discord_webhooks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS seen_events (
    event_key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    repository TEXT NOT NULL,
    event_type TEXT NOT NULL,
    result TEXT NOT NULL,
    title TEXT,
    actor TEXT,
    reason TEXT
);
'''

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

def close_db(_=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    path = app.config['DATABASE']
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with sqlite3.connect(path, timeout=30) as con:
        con.executescript(SCHEMA)
    app.teardown_appcontext(close_db)

def setting_get(key, default=None):
    row = get_db().execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default

def setting_set(key, value):
    db = get_db()
    db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
    db.commit()
