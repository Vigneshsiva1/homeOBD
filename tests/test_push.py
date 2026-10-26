from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db, engine, push
from app.main import create_app

TZ = timezone(timedelta(hours=-5))
TODAY = date(2026, 10, 28)  # a Wednesday


def code(c, interval, minutes, ago, snoozed=False):
    now = datetime(2026, 10, 28, 12, tzinfo=TZ)
    until = now + timedelta(hours=1) if snoozed else None
    return engine.evaluate(c, c, interval, TODAY - timedelta(days=ago), until, TODAY, now, minutes=minutes)


@pytest.mark.parametrize(
    "interval, minutes, tier",
    [(1, 20, "quick"), (2, 10, "quick"), (3, 5, "standard"), (14, 59, "standard"), (2, 60, "long"), (90, 120, "long")],
)
def test_notify_tier(interval, minutes, tier):
    assert engine.notify_tier(interval, minutes) == tier


def test_slot_rules():
    dishes = code("K0001", 1, 20, 1)      # quick, due
    shower = code("B1004", 14, 30, 14)    # standard, due
    oven = code("K1004", 90, 90, 90)      # long, due
    snoozed = code("B0002", 7, 10, 7, snoozed=True)
    ok = code("L1001", 14, 20, 0)         # not due
    codes = [dishes, shower, oven, snoozed, ok]
    wed, sat = 2, 5
    names = lambda slot, day: [c.code for c in engine.slot_codes(slot, day, codes)]
    assert names("eve", wed) == ["K0001"]            # quick: 8 pm, any day
    assert names("am", wed) == ["B1004"]             # standard: 8 am
    assert names("pm", wed) == ["B1004"]             # standard: 6 pm on weekdays
    assert sorted(names("am", sat)) == ["B1004", "K1004"]  # weekend 8 am adds long tasks
    assert names("pm", sat) == ["K1004"]             # weekend 6 pm: long only
    assert "K1004" not in names("am", wed) + names("pm", wed) + names("eve", wed)  # never weekdays


def test_notification_text():
    one = engine.notification_text([code("K0001", 1, 20, 1)])
    assert one == ("K0001 K0001", "Due today · about 20 min")
    many = engine.notification_text([code(f"K000{i}", 1, 5, 1) for i in range(1, 7)])
    assert many[0] == "6 chores due"
    assert many[1].splitlines()[-1] == "+2 more"


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "t.db"
    db.init(path, datetime.now().astimezone())
    c = db.connect(path)
    yield c
    c.close()


def test_keys_are_created_once_and_private_key_stays_put(conn):
    key = push.public_key(conn)
    assert len(key) == 87 and push.public_key(conn) == key  # 65-byte P-256 point, base64url
    assert "PRIVATE KEY" in conn.execute("SELECT private_pem FROM push_keys").fetchone()[0]


def test_send_all_drops_gone_subscriptions(conn):
    at = datetime.now().astimezone()
    push.subscribe(conn, "https://push.example/a", "p", "a", "ua", at)
    push.subscribe(conn, "https://push.example/b", "p", "a", "ua", at)
    sent = []

    def sender(sub, payload):
        if sub["endpoint"].endswith("/b"):
            raise push.Gone()
        sent.append((sub["endpoint"], payload))

    assert push.send_all(conn, "T", "B", "tag", sender=sender) == {"sent": 1, "removed": 1, "failed": 0}
    assert push.subscription_count(conn) == 1
    assert '"title": "T"' in sent[0][1]


def test_run_schedule_fires_each_slot_once(conn):
    push.subscribe(conn, "https://push.example/a", "p", "a", "ua", datetime.now().astimezone())
    calls = []
    sender = lambda sub, payload: calls.append(payload)
    # Make the daily dishes chore due today.
    conn.execute("UPDATE chores SET last_done_at = ?, minutes = 20 WHERE code = 'K0001'",
                 ((datetime.now().astimezone() - timedelta(days=1)).isoformat(),))
    conn.commit()
    today = datetime.now().astimezone().date()
    at = datetime.combine(today, engine.SLOTS["eve"], tzinfo=datetime.now().astimezone().tzinfo) + timedelta(minutes=3)
    assert push.run_schedule(conn, at, sender=sender) == ["eve"]
    assert any("K0001" in p for p in calls)
    assert push.run_schedule(conn, at + timedelta(minutes=5), sender=sender) == []  # not twice
    late = at + engine.SLOT_GRACE
    assert push.run_schedule(conn, late.replace(day=late.day), sender=sender) == []


def test_slot_outside_grace_is_skipped(conn):
    today = datetime.now().astimezone().date()
    tz = datetime.now().astimezone().tzinfo
    at = datetime.combine(today, engine.SLOTS["am"], tzinfo=tz) + engine.SLOT_GRACE + timedelta(minutes=1)
    assert "am" not in push.run_schedule(conn, at, sender=lambda s, p: None)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.db", tick=False)) as c:
        yield c


def test_push_api(client, monkeypatch):
    key = client.get("/api/push/key").json()["public_key"]
    assert len(key) == 87
    assert client.post("/api/push/test").status_code == 409  # nobody subscribed yet
    sub = {"endpoint": "https://web.push.apple.com/abc", "keys": {"p256dh": "x", "auth": "y"}}
    assert client.post("/api/push/subscribe", json=sub).json() == {"devices": 1}
    assert client.post("/api/push/subscribe", json=sub).json() == {"devices": 1}  # same phone again
    assert client.post("/api/push/subscribe", json={**sub, "endpoint": "http://evil"}).status_code == 422
    sent = []
    monkeypatch.setattr(push, "webpush_sender", lambda conn: lambda s, p: sent.append(p))
    assert client.post("/api/push/test").json() == {"sent": 1, "removed": 0, "failed": 0}
    assert client.get("/api/push/status").json()["slots"] == {"am": "08:00", "pm": "18:00", "eve": "20:00"}
    assert client.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]}).json() == {"devices": 0}
    assert "private" not in str(client.get("/api/settings").json()).lower()


def test_minutes_field(client):
    r = client.patch("/api/chores/K0001", json={"minutes": 25})
    assert (r.json()["minutes"], r.json()["notify"]) == (25, "quick")
    assert client.patch("/api/chores/K0001", json={"minutes": 0}).status_code == 422


def test_fixed_notify_slot_overrides_the_tier():
    unload = engine.evaluate("K0005", "Unload", 1, TODAY - timedelta(days=1), None, TODAY,
                             datetime(2026, 10, 28, 12, tzinfo=TZ), minutes=10, notify_slot="am")
    load = engine.evaluate("K0001", "Load", 1, TODAY - timedelta(days=1), None, TODAY,
                           datetime(2026, 10, 28, 12, tzinfo=TZ), minutes=10, notify_slot="eve")
    codes = [unload, load]
    for day in (2, 5):  # every day, weekday or weekend
        assert [c.code for c in engine.slot_codes("am", day, codes)] == ["K0005"]
        assert [c.code for c in engine.slot_codes("eve", day, codes)] == ["K0001"]
        assert engine.slot_codes("pm", day, codes) == []


def test_notify_slot_api(client):
    assert client.get("/api/codes/K0001").json()["notify_slot"] == "auto"
    assert client.patch("/api/chores/K0001", json={"notify_slot": "am"}).json()["notify_slot"] == "am"
    assert client.patch("/api/chores/K0001", json={"notify_slot": "auto"}).json()["notify_slot"] == "auto"
    assert client.patch("/api/chores/K0001", json={"notify_slot": "noon"}).status_code == 422
    r = client.post("/api/chores", json={"zone": "K", "category": 0, "name": "Unload", "interval_days": 1, "notify_slot": "am"})
    assert r.json()["notify_slot"] == "am"
