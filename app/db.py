"""SQLite storage: schema, connections and first-run seed data."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS chores (
    id            INTEGER PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    interval_days INTEGER NOT NULL CHECK (interval_days > 0),
    last_done_at  TEXT NOT NULL,
    snoozed_until TEXT,
    trigger_type  TEXT NOT NULL DEFAULT 'schedule',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS completions (
    id       INTEGER PRIMARY KEY,
    chore_id INTEGER NOT NULL REFERENCES chores(id) ON DELETE CASCADE,
    done_at  TEXT NOT NULL,
    note     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS freeze_frames (
    id            INTEGER PRIMARY KEY,
    chore_id      INTEGER NOT NULL REFERENCES chores(id) ON DELETE CASCADE,
    set_at        TEXT NOT NULL,
    health_at_set INTEGER NOT NULL,
    streak_at_set INTEGER NOT NULL,
    cleared_at    TEXT
);
CREATE TABLE IF NOT EXISTS daily_health (
    date          TEXT PRIMARY KEY,
    health        INTEGER NOT NULL,
    overdue_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {"unit_id": "APT-01", "theme": "classic"}

# (code, name, interval_days, days since last done). The offsets reproduce the prototype's
# demo state: K2002 PERM, L0002 and K0001 CONF, B1004 and U2001 PEND, everything else OK.
SEED_CHORES = [
    ("K0001", "Wash dishes", 1, 2),
    ("K0002", "Wipe counters & stovetop", 2, 0),
    ("K0003", "Take out trash & recycling", 3, 1),
    ("K1001", "Clean fridge interior", 30, 10),
    ("K2001", "Degrease range-hood filter", 90, 30),
    ("K2002", "Clean fridge coils", 180, 380),
    ("K2003", "Descale kettle", 30, 9),
    ("B0001", "Clean toilet & sink", 7, 2),
    ("B1004", "Scrub shower", 14, 13),
    ("B2001", "Clean bath fan", 60, 13),
    ("L0002", "Vacuum living room", 7, 10),
    ("L1001", "Dust surfaces", 14, 5),
    ("R0001", "Vacuum bedroom", 7, 3),
    ("R1001", "Change bed sheets", 14, 4),
    ("U1001", "Run washer cleaning cycle", 30, 12),
    ("U2001", "Replace HVAC filter", 90, 87),
    ("G0001", "Water plants", 4, 1),
    ("G2001", "Test smoke alarms", 180, 171),
]


def connect(path: str | Path) -> sqlite3.Connection:
    # FastAPI may open a request's connection and use it on different threadpool threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(path: str | Path, now: datetime) -> None:
    """Create the schema, and seed chores and settings on first run."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", DEFAULT_SETTINGS.items()
        )
        if conn.execute("SELECT COUNT(*) FROM chores").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO chores (code, name, interval_days, last_done_at, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (code, name, interval, (now - timedelta(days=ago)).isoformat(), now.isoformat())
                    for code, name, interval, ago in SEED_CHORES
                ],
            )
    conn.close()
