"""Operations that combine the database with the state engine. Shared by the API and the
background tick. Callers pass `at` (an aware local datetime) so tests can control time."""

import sqlite3
from datetime import date, datetime, timedelta

from . import engine


def now() -> datetime:
    return datetime.now().astimezone()


def local_date(ts: str) -> date:
    return datetime.fromisoformat(ts).astimezone().date()


def _to_code(row: sqlite3.Row, at: datetime) -> engine.Code:
    snoozed = datetime.fromisoformat(row["snoozed_until"]) if row["snoozed_until"] else None
    return engine.evaluate(
        row["code"],
        row["name"],
        row["interval_days"],
        local_date(row["last_done_at"]),
        snoozed,
        at.date(),
        at,
        row["description"],
        row["how_to"],
        row["done_when"],
    )


def load_codes(conn: sqlite3.Connection, at: datetime) -> list[engine.Code]:
    rows = conn.execute("SELECT * FROM chores ORDER BY code").fetchall()
    return [_to_code(r, at) for r in rows]


def get_code(conn: sqlite3.Connection, code: str, at: datetime) -> engine.Code | None:
    row = conn.execute("SELECT * FROM chores WHERE code = ?", (code,)).fetchone()
    return _to_code(row, at) if row else None


def history(conn: sqlite3.Connection) -> dict[date, int]:
    rows = conn.execute("SELECT date, overdue_count FROM daily_health").fetchall()
    return {date.fromisoformat(r["date"]): r["overdue_count"] for r in rows}


def streaks(conn: sqlite3.Connection, codes: list[engine.Code], at: datetime) -> tuple[int, int]:
    return engine.streaks(history(conn), at.date(), engine.overdue_count(codes))


def sync(conn: sqlite3.Connection, at: datetime) -> None:
    """Record today's health for streaks, capture freeze frames for newly overdue codes and
    close the frames of codes that are no longer overdue."""
    codes = load_codes(conn, at)
    health = engine.health(codes)
    conn.execute(
        "INSERT INTO daily_health (date, health, overdue_count) VALUES (?, ?, ?)"
        " ON CONFLICT(date) DO UPDATE SET health = excluded.health,"
        " overdue_count = excluded.overdue_count",
        (at.date().isoformat(), health, engine.overdue_count(codes)),
    )
    # The streak a code broke: the run that ended yesterday.
    streak_before = engine.current_streak(history(conn), at.date() - timedelta(days=1))
    for c in codes:
        if not engine.is_overdue(c.state):
            # No longer overdue (e.g. its last-done date was edited): close any open frame.
            conn.execute(
                "UPDATE freeze_frames SET cleared_at = ? WHERE cleared_at IS NULL"
                " AND chore_id = (SELECT id FROM chores WHERE code = ?)",
                (at.isoformat(), c.code),
            )
        else:
            conn.execute(
                "INSERT INTO freeze_frames (chore_id, set_at, health_at_set, streak_at_set)"
                " SELECT id, ?, ?, ? FROM chores WHERE code = ? AND NOT EXISTS ("
                "  SELECT 1 FROM freeze_frames f"
                "  WHERE f.chore_id = chores.id AND f.cleared_at IS NULL)",
                (at.isoformat(), health, streak_before, c.code),
            )
    conn.commit()


def mark_done(conn: sqlite3.Connection, code: str, at: datetime, note: str = "") -> bool:
    """Clear a code: reset its timer, log the completion, drop its snooze and freeze frame."""
    row = conn.execute("SELECT id FROM chores WHERE code = ?", (code,)).fetchone()
    if row is None:
        return False
    ts = at.isoformat()
    conn.execute(
        "UPDATE chores SET last_done_at = ?, snoozed_until = NULL WHERE id = ?", (ts, row["id"])
    )
    conn.execute(
        "INSERT INTO completions (chore_id, done_at, note) VALUES (?, ?, ?)", (row["id"], ts, note)
    )
    conn.execute(
        "UPDATE freeze_frames SET cleared_at = ? WHERE chore_id = ? AND cleared_at IS NULL",
        (ts, row["id"]),
    )
    sync(conn, at)
    return True


def erase(conn: sqlite3.Connection, at: datetime) -> tuple[list[str], int]:
    """Snooze active non-PERM codes for 24 h. Returns (erased codes, PERM codes still active)."""
    codes = load_codes(conn, at)
    erased = [c.code for c in engine.erasable(codes)]
    until = (at + engine.SNOOZE).isoformat()
    conn.executemany(
        "UPDATE chores SET snoozed_until = ? WHERE code = ?", [(until, c) for c in erased]
    )
    conn.commit()
    perm = sum(c.state == "PERM" for c in engine.active_codes(codes))
    return erased, perm


def freeze_frame(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT f.set_at, f.health_at_set, f.streak_at_set FROM freeze_frames f"
        " JOIN chores c ON c.id = f.chore_id"
        " WHERE c.code = ? AND f.cleared_at IS NULL ORDER BY f.id DESC LIMIT 1",
        (code,),
    ).fetchone()


def next_code(conn: sqlite3.Connection, zone: str, category: int) -> str:
    """First unused code for a zone and category, e.g. K0004 after K0001..K0003."""
    prefix = f"{zone}{category}"
    rows = conn.execute("SELECT code FROM chores WHERE code LIKE ?", (prefix + "%",)).fetchall()
    used = {int(r["code"][2:]) for r in rows}
    seq = next(n for n in range(1, 1001) if n not in used)
    if seq > 999:
        raise ValueError(f"no free codes left for {prefix}")
    return f"{prefix}{seq:03d}"
