from datetime import date, datetime, timedelta, timezone

import pytest

from app import engine

TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def code(c="L0002", interval=7, ago=0, snoozed_until=None):
    return engine.evaluate(c, "Chore", interval, TODAY - timedelta(days=ago), snoozed_until, TODAY, NOW)


@pytest.mark.parametrize("interval, window", [(1, 1), (4, 1), (7, 1), (14, 2), (30, 4), (90, 7), (180, 7)])
def test_pend_window(interval, window):
    assert engine.pend_window(interval) == window


@pytest.mark.parametrize(
    "interval, left, expected",
    [
        (7, 2, "OK"),
        (7, 1, "OK"),
        (7, 0, "PEND"),
        (7, -1, "CONF"),
        (7, -6, "CONF"),
        (7, -7, "PERM"),
        (14, 2, "OK"),
        (14, 1, "PEND"),
        (1, 0, "PEND"),
        (1, -1, "CONF"),  # daily chores aren't PERM after one day...
        (1, -6, "CONF"),
        (1, -7, "PERM"),  # ...only after PERM_MIN_DAYS
        (180, 7, "OK"),
        (180, 6, "PEND"),
        (180, -179, "CONF"),
        (180, -180, "PERM"),
    ],
)
def test_state_boundaries(interval, left, expected):
    assert engine.state(left, interval) == expected


@pytest.mark.parametrize("left, text", [(-3, "Overdue 3 d"), (0, "Due today"), (1, "Due in 1 d")])
def test_status_text(left, text):
    assert engine.status_text(left) == text


def test_prototype_examples():
    # Values from the prototype's mock data.
    assert code("K2002", 180, 380).status == "Overdue 200 d"
    assert code("K2002", 180, 380).state == "PERM"
    assert code("L0002", 7, 10).state == "CONF"
    assert code("K0001", 1, 2).state == "CONF"
    assert code("B1004", 14, 13).status == "Due in 1 d"
    assert code("B1004", 14, 13).state == "PEND"
    assert code("U2001", 90, 87).state == "PEND"


def test_code_properties():
    c = code("K2002", 180, 0)
    assert (c.zone, c.zone_name, c.category) == ("K", "Kitchen", 2)


def test_snooze_hides_code_until_it_expires():
    assert not code(ago=10, snoozed_until=NOW + timedelta(hours=1)).active
    assert code(ago=10, snoozed_until=NOW - timedelta(seconds=1)).active
    assert not code(ago=0).active  # OK codes are never active


def test_active_codes_sorted_worst_first():
    codes = [
        code("B1004", 14, 13),  # PEND
        code("K0001", 1, 2),  # CONF, overdue 1
        code("K2002", 180, 380),  # PERM
        code("L0002", 7, 10),  # CONF, overdue 3
        code("B0001", 7, 2),  # OK
    ]
    assert [c.code for c in engine.active_codes(codes)] == ["K2002", "L0002", "K0001", "B1004"]
    assert [c.code for c in engine.erasable(codes)] == ["L0002", "K0001", "B1004"]


def test_health_and_lamp():
    snoozed = NOW + timedelta(hours=1)
    codes = [code("L0002", 7, 10, snoozed), code("B0001", 7, 0), code("R0001", 7, 0), code("G0001", 4, 0)]
    assert engine.health(codes) == 75  # snoozing doesn't improve health
    assert not engine.lamp_on(codes)  # but it does turn the lamp off
    assert engine.lamp_on([code("L0002", 7, 10)])
    assert not engine.lamp_on([code("B1004", 14, 13)])  # PEND alone doesn't light it
    assert engine.health([]) == 100


def test_readiness():
    snoozed = NOW + timedelta(hours=1)
    codes = [code("K0001", 1, 2), code("B1004", 14, 13), code("R0001", 7, 6, snoozed)]
    r = engine.readiness(codes)
    assert r["K"] == "INC"  # overdue
    assert r["B"] == "RDY"  # pending only
    assert r["R"] == "INC"  # snoozed
    assert r["L"] == r["U"] == r["G"] == "RDY"


def test_service_due_is_category_2_by_days_left():
    codes = [code("U2001", 90, 87), code("K2002", 180, 380), code("L0002", 7, 10), code("G2001", 180, 171)]
    assert [c.code for c in engine.service_due(codes)] == ["K2002", "U2001", "G2001"]


def d(n):
    return TODAY - timedelta(days=n)


def test_streaks():
    history = {d(5): 0, d(4): 0, d(3): 1, d(2): 0, d(1): 0}
    assert engine.streaks(history, TODAY, 0) == (3, 3)  # d2, d1, today
    assert engine.streaks(history, TODAY, 2) == (0, 2)  # overdue today breaks the run
    # Today's live count overrides an earlier record for today.
    assert engine.streaks({**history, TODAY: 4}, TODAY, 0) == (3, 3)


def test_streak_broken_by_missing_day():
    history = {d(4): 0, d(3): 0, d(1): 0}  # Pi was off on d(2)
    assert engine.streaks(history, TODAY, 0) == (2, 2)
    assert engine.current_streak(history, d(3)) == 2
