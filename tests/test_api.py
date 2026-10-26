from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db", tick=False)) as c:
        yield c


def codes(client):
    return [(c["code"], c["state"]) for c in client.get("/api/codes").json()["codes"]]


def test_seed_matches_prototype(client):
    body = client.get("/api/codes").json()
    assert [(c["code"], c["state"]) for c in body["codes"]] == [
        ("K2002", "PERM"),
        ("L0002", "CONF"),
        ("K0001", "CONF"),
        ("B1004", "PEND"),
        ("U2001", "PEND"),
    ]
    assert body["codes"][0]["status"] == "Overdue 200 d"
    assert body["lamp"] is True


def test_live_data(client):
    live = client.get("/api/live").json()
    assert live == {
        "health": 83,  # 15 of 18 not overdue, as in the prototype
        "overdue": 3,
        "pending": 2,
        "lamp": True,
        "streak": 0,
        "best_streak": 0,
        "next_service": {"code": "U2001", "name": "Replace HVAC filter", "days_left": 3},
        "tasks": 18,
    }


def test_code_detail_and_404(client):
    c = client.get("/api/codes/B1004").json()
    assert (c["name"], c["zone_name"], c["status"], c["interval_days"]) == ("Scrub shower", "Bath", "Due in 1 d", 14)
    assert client.get("/api/codes/X9999").status_code == 404


def test_mark_done_clears_code_and_freeze_frame(client):
    frame = client.get("/api/codes/L0002/freeze").json()["frame"]
    assert frame == {"set_on": date.today().isoformat(), "health_at_set": 83, "streak_at_set": 0}

    r = client.post("/api/codes/L0002/done", json={"note": "done properly"})
    assert r.status_code == 200
    assert r.json()["health"] == 89

    assert "L0002" not in dict(codes(client))
    detail = client.get("/api/codes/L0002").json()
    assert (detail["state"], detail["last_done"]) == ("OK", date.today().isoformat())
    assert client.get("/api/codes/L0002/freeze").json()["frame"] is None
    assert client.post("/api/codes/X9999/done").status_code == 404


def test_pending_code_has_no_freeze_frame(client):
    assert client.get("/api/codes/B1004/freeze").json()["frame"] is None


def test_erase_snoozes_all_but_perm(client):
    r = client.post("/api/codes/erase").json()
    assert sorted(r["erased"]) == ["B1004", "K0001", "L0002", "U2001"]
    assert r["permanent_remaining"] == 1
    assert r["lamp"] is True  # K2002 is PERM and keeps the lamp on
    assert codes(client) == [("K2002", "PERM")]
    assert client.get("/api/live").json()["health"] == 83  # the chores still wait

    client.post("/api/codes/K2002/done")
    assert codes(client) == []
    assert client.get("/api/live").json()["lamp"] is False


def test_readiness(client):
    r = client.get("/api/readiness").json()
    assert {z["zone"]: z["status"] for z in r["zones"]} == {
        "K": "INC", "B": "RDY", "L": "INC", "R": "RDY", "U": "RDY", "G": "RDY",
    }
    assert (r["ready"], r["total"]) == (4, 6)


def test_service_due(client):
    items = client.get("/api/service").json()["items"]
    assert [(i["code"], i["days_left"]) for i in items] == [
        ("K2002", -200), ("U2001", 3), ("G2001", 9), ("K2003", 21), ("B2001", 47), ("K2001", 60),
    ]


def test_unit_info(client):
    u = client.get("/api/unit").json()
    assert (u["unit_id"], u["zones"], u["tasks"]) == ("APT-01", 6, 18)
    assert u["software"].startswith("APT-OBD ")


def test_create_chore_with_auto_code(client):
    r = client.post("/api/chores", json={"zone": "K", "category": 0, "name": "Clean sink", "interval_days": 3})
    assert r.status_code == 201
    assert (r.json()["code"], r.json()["state"]) == ("K0004", "OK")
    assert client.get("/api/unit").json()["tasks"] == 19


def test_create_chore_validation(client):
    base = {"name": "Thing", "interval_days": 7}
    assert client.post("/api/chores", json={**base, "code": "L0002"}).status_code == 409
    assert client.post("/api/chores", json={**base, "code": "X0001"}).status_code == 422
    assert client.post("/api/chores", json={**base, "code": "K4001"}).status_code == 422
    assert client.post("/api/chores", json=base).status_code == 422
    assert client.post("/api/chores", json={**base, "code": "R2001", "interval_days": 0}).status_code == 422
    last = (date.today() - timedelta(days=10)).isoformat()
    r = client.post("/api/chores", json={**base, "code": "R2001", "last_done": last})
    assert (r.status_code, r.json()["state"]) == (201, "CONF")


def test_update_and_delete_chore(client):
    r = client.patch("/api/chores/L0002", json={"interval_days": 30, "name": "Vacuum lounge"})
    assert (r.json()["name"], r.json()["interval_days"], r.json()["state"]) == ("Vacuum lounge", 30, "OK")
    assert client.patch("/api/chores/X9999", json={"name": "x"}).status_code == 404

    assert client.delete("/api/chores/L0002").status_code == 204
    assert client.get("/api/codes/L0002").status_code == 404
    assert client.delete("/api/chores/L0002").status_code == 404
    assert len(client.get("/api/chores").json()["chores"]) == 17


def test_settings(client):
    assert client.get("/api/settings").json() == {"unit_id": "APT-01", "theme": "classic"}
    assert client.put("/api/settings", json={"theme": "amber"}).json()["theme"] == "amber"
    assert client.put("/api/settings", json={"theme": "pink"}).status_code == 422


def test_meta(client):
    m = client.get("/api/meta").json()
    assert [z["zone"] for z in m["zones"]] == ["K", "B", "L", "R", "U", "G"]
    assert [c["category"] for c in m["categories"]] == [0, 1, 2, 3]
    assert m["themes"] == ["classic", "amber", "green"]


@pytest.mark.parametrize(
    "path, marker",
    [
        ("/", 'id="screen"'),
        ("/setup", 'id="chore-form"'),
        ("/static/scantool.js", "function view()"),
        ("/static/setup.js", "async function loadChores()"),
    ],
)
def test_pages_are_served(client, path, marker):
    r = client.get(path)
    assert r.status_code == 200
    assert marker in r.text


def test_fonts_are_served(client):
    r = client.get("/static/fonts/vt323-400-latin.woff2")
    assert r.status_code == 200
    assert r.content[:4] == b"wOF2"


def test_help_fields_round_trip(client):
    assert client.get("/api/codes/K0001").json()["how_to"] == ""
    r = client.patch("/api/chores/K0001", json={"how_to": "1. Scrape\n2. Wash", "done_when": "Sink empty."})
    assert (r.json()["how_to"], r.json()["done_when"]) == ("1. Scrape\n2. Wash", "Sink empty.")
    r = client.post(
        "/api/chores",
        json={"zone": "B", "category": 0, "name": "Wash towels", "interval_days": 7, "how_to": "Hot wash.", "done_when": "Fresh towels out."},
    )
    assert (r.json()["how_to"], r.json()["done_when"]) == ("Hot wash.", "Fresh towels out.")


def test_old_database_gains_help_columns(tmp_path):
    import sqlite3
    from datetime import datetime, timezone

    from app import db

    path = tmp_path / "old.db"
    old_schema = db.SCHEMA.replace("    how_to        TEXT NOT NULL DEFAULT '',\n", "").replace(
        "    done_when     TEXT NOT NULL DEFAULT '',\n", ""
    )
    conn = sqlite3.connect(path)
    conn.executescript(old_schema)
    conn.execute(
        "INSERT INTO chores (code, name, interval_days, last_done_at, created_at) VALUES ('K0001', 'Dishes', 1, ?, ?)",
        ("2026-10-01T12:00:00+00:00", "2026-10-01T12:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    db.init(path, datetime(2026, 10, 2, tzinfo=timezone.utc))
    conn = db.connect(path)
    row = conn.execute("SELECT name, how_to, done_when FROM chores WHERE code = 'K0001'").fetchone()
    assert (row["name"], row["how_to"], row["done_when"]) == ("Dishes", "", "")


def test_editing_last_done_closes_freeze_frame(client):
    assert client.get("/api/codes/K0001/freeze").json()["frame"] is not None
    client.patch("/api/chores/K0001", json={"last_done": date.today().isoformat()})
    assert client.get("/api/codes/K0001/freeze").json()["frame"] is None


def test_home_screen_app_files(client):
    m = client.get("/manifest.webmanifest")
    assert m.headers["content-type"].startswith("application/manifest+json")
    assert (m.json()["display"], m.json()["start_url"]) == ("standalone", "/")
    for icon in m.json()["icons"]:
        assert client.get(icon["src"]).content[:8] == b"\x89PNG\r\n\x1a\n"
    sw = client.get("/sw.js")
    assert sw.headers["content-type"].startswith("text/javascript")
    assert sw.headers["cache-control"] == "no-cache"
    assert "/api/" in sw.text  # API requests bypass the cache
    page = client.get("/").text
    assert 'rel="manifest"' in page and 'rel="apple-touch-icon"' in page
    assert client.get("/static/icons/apple-touch-icon.png").status_code == 200
