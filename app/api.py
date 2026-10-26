"""JSON API under /api. Scan-tool screens use /api/codes and friends; the Setup page uses
/api/chores and /api/settings."""

import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import __version__, db, engine, service

router = APIRouter(prefix="/api")

THEMES = ("classic", "amber", "green")


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


Conn = Depends(get_conn)


def code_json(c: engine.Code) -> dict:
    return {
        "code": c.code,
        "name": c.name,
        "description": c.description,
        "how_to": c.how_to,
        "done_when": c.done_when,
        "zone": c.zone,
        "zone_name": c.zone_name,
        "category": c.category,
        "category_name": engine.CATEGORIES[c.category],
        "state": c.state,
        "status": c.status,
        "interval_days": c.interval_days,
        "last_done": c.last_done.isoformat(),
        "days_left": c.days_left,
        "snoozed": c.snoozed,
    }


def _require(c: engine.Code | None, code: str) -> engine.Code:
    if c is None:
        raise HTTPException(404, f"Unknown code {code}")
    return c


def _done_timestamp(d: date, at: datetime) -> str:
    return datetime.combine(d, at.timetz()).isoformat()


# --- Scan-tool screens -------------------------------------------------------------------


@router.get("/codes")
def read_codes(conn: sqlite3.Connection = Conn):
    codes = service.load_codes(conn, service.now())
    return {"codes": [code_json(c) for c in engine.active_codes(codes)], "lamp": engine.lamp_on(codes)}


@router.post("/codes/erase")
def erase_codes(conn: sqlite3.Connection = Conn):
    at = service.now()
    erased, perm = service.erase(conn, at)
    return {
        "erased": erased,
        "permanent_remaining": perm,
        "lamp": engine.lamp_on(service.load_codes(conn, at)),
    }


@router.get("/codes/{code}")
def read_code(code: str, conn: sqlite3.Connection = Conn):
    return code_json(_require(service.get_code(conn, code, service.now()), code))


class DoneIn(BaseModel):
    note: str = Field("", max_length=200)


@router.post("/codes/{code}/done")
def mark_done(code: str, body: DoneIn | None = None, conn: sqlite3.Connection = Conn):
    at = service.now()
    if not service.mark_done(conn, code, at, body.note if body else ""):
        raise HTTPException(404, f"Unknown code {code}")
    codes = service.load_codes(conn, at)
    return {"code": code, "health": engine.health(codes), "lamp": engine.lamp_on(codes)}


@router.get("/codes/{code}/freeze")
def read_freeze_frame(code: str, conn: sqlite3.Connection = Conn):
    at = service.now()
    c = _require(service.get_code(conn, code, at), code)
    service.sync(conn, at)  # don't miss a code that went overdue since the last tick
    f = service.freeze_frame(conn, code)
    frame = (
        {
            "set_on": service.local_date(f["set_at"]).isoformat(),
            "health_at_set": f["health_at_set"],
            "streak_at_set": f["streak_at_set"],
        }
        if f
        else None
    )
    return {"code": code_json(c), "frame": frame}


@router.get("/live")
def live_data(conn: sqlite3.Connection = Conn):
    at = service.now()
    codes = service.load_codes(conn, at)
    streak, best = service.streaks(conn, codes, at)
    upcoming = [c for c in engine.service_due(codes) if c.days_left >= 0]
    nxt = upcoming[0] if upcoming else None
    return {
        "health": engine.health(codes),
        "overdue": engine.overdue_count(codes),
        "pending": sum(c.state == "PEND" for c in engine.active_codes(codes)),
        "lamp": engine.lamp_on(codes),
        "streak": streak,
        "best_streak": best,
        "next_service": {"code": nxt.code, "name": nxt.name, "days_left": nxt.days_left} if nxt else None,
        "tasks": len(codes),
    }


@router.get("/readiness")
def read_readiness(conn: sqlite3.Connection = Conn):
    ready = engine.readiness(service.load_codes(conn, service.now()))
    zones = [{"zone": z, "name": engine.ZONES[z], "status": s} for z, s in ready.items()]
    return {"zones": zones, "ready": sum(s == "RDY" for s in ready.values()), "total": len(zones)}


@router.get("/service")
def read_service(conn: sqlite3.Connection = Conn):
    codes = engine.service_due(service.load_codes(conn, service.now()))
    return {"items": [{"code": c.code, "name": c.name, "days_left": c.days_left} for c in codes]}


def _board_model() -> str:
    try:
        model = Path("/proc/device-tree/model").read_text().strip("\x00\n ")
    except OSError:
        return "Unknown"
    return model.split(" Model")[0]  # "Raspberry Pi 4 Model B Rev 1.5" -> "Raspberry Pi 4"


@router.get("/unit")
def unit_info(conn: sqlite3.Connection = Conn):
    unit_id = conn.execute("SELECT value FROM settings WHERE key = 'unit_id'").fetchone()[0]
    tasks = conn.execute("SELECT COUNT(*) FROM chores").fetchone()[0]
    return {
        "unit_id": unit_id,
        "software": f"APT-OBD {__version__}",
        "ecu": _board_model(),
        "interface": "Web, Wi-Fi",
        "zones": len(engine.ZONES),
        "tasks": tasks,
    }


# --- Setup page ----------------------------------------------------------------------------


@router.get("/meta")
def meta():
    return {
        "zones": [{"zone": z, "name": n} for z, n in engine.ZONES.items()],
        "categories": [{"category": k, "name": n} for k, n in engine.CATEGORIES.items()],
        "themes": list(THEMES),
    }


@router.get("/chores")
def list_chores(conn: sqlite3.Connection = Conn):
    return {"chores": [code_json(c) for c in service.load_codes(conn, service.now())]}


class ChoreIn(BaseModel):
    code: str | None = None
    zone: str | None = None
    category: int | None = Field(None, ge=0, le=3)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=500)
    how_to: str = Field("", max_length=2000)
    done_when: str = Field("", max_length=500)
    interval_days: int = Field(ge=1, le=3650)
    last_done: date | None = None


@router.post("/chores", status_code=201)
def create_chore(body: ChoreIn, conn: sqlite3.Connection = Conn):
    at = service.now()
    if body.code:
        if not engine.CODE_RE.match(body.code):
            raise HTTPException(422, "Code must be a zone letter (KBLRUG) and 4 digits, first 0-3")
        code = body.code
    elif body.zone in engine.ZONES and body.category is not None:
        try:
            code = service.next_code(conn, body.zone, body.category)
        except ValueError as e:
            raise HTTPException(409, str(e))
    else:
        raise HTTPException(422, "Give either a code, or a zone and category")
    last_done = _done_timestamp(body.last_done, at) if body.last_done else at.isoformat()
    try:
        conn.execute(
            "INSERT INTO chores (code, name, description, how_to, done_when, interval_days,"
            " last_done_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code,
                body.name,
                body.description,
                body.how_to,
                body.done_when,
                body.interval_days,
                last_done,
                at.isoformat(),
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Code {code} already exists")
    conn.commit()
    return code_json(service.get_code(conn, code, at))


class ChorePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = Field(None, max_length=500)
    how_to: str | None = Field(None, max_length=2000)
    done_when: str | None = Field(None, max_length=500)
    interval_days: int | None = Field(None, ge=1, le=3650)
    last_done: date | None = None


@router.patch("/chores/{code}")
def update_chore(code: str, body: ChorePatch, conn: sqlite3.Connection = Conn):
    at = service.now()
    _require(service.get_code(conn, code, at), code)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    if "last_done" in fields:
        fields["last_done_at"] = _done_timestamp(fields.pop("last_done"), at)
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)  # keys come from ChorePatch only
        conn.execute(f"UPDATE chores SET {assignments} WHERE code = ?", (*fields.values(), code))
        conn.commit()
    return code_json(service.get_code(conn, code, at))


@router.delete("/chores/{code}", status_code=204)
def delete_chore(code: str, conn: sqlite3.Connection = Conn):
    if conn.execute("DELETE FROM chores WHERE code = ?", (code,)).rowcount == 0:
        raise HTTPException(404, f"Unknown code {code}")
    conn.commit()
    return Response(status_code=204)


@router.get("/settings")
def read_settings(conn: sqlite3.Connection = Conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


class SettingsIn(BaseModel):
    theme: Literal[THEMES] | None = None
    unit_id: str | None = Field(None, min_length=1, max_length=12)


@router.put("/settings")
def update_settings(body: SettingsIn, conn: sqlite3.Connection = Conn):
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        body.model_dump(exclude_none=True).items(),
    )
    conn.commit()
    return read_settings(conn)
