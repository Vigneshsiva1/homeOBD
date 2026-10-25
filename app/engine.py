"""State engine: turns chore data into scan-tool codes and the values derived from them.

Everything here works on plain values (dates, ints) so it can be tested without a database
and reused later for sensor rules. Rules are documented in docs/PLAN.md.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

ZONES = {
    "K": "Kitchen",
    "B": "Bath",
    "L": "Living",
    "R": "Bedroom",
    "U": "Utility",
    "G": "Whole apt",
}
CATEGORIES = {0: "Routine", 1: "Deep clean", 2: "Service", 3: "Sensor"}
CODE_RE = re.compile(r"^[KBLRUG][0-3]\d{3}$")

# PEND starts this many days before the due date: 15% of the interval, clamped to 1..7 days.
PEND_FRACTION = 0.15
PEND_MIN_DAYS = 1
PEND_MAX_DAYS = 7
# PERM once overdue by a full interval, but never sooner than this many days.
PERM_MIN_DAYS = 7
SNOOZE = timedelta(hours=24)

STATE_RANK = {"PERM": 0, "CONF": 1, "PEND": 2, "OK": 3}


def pend_window(interval_days: int) -> int:
    return min(PEND_MAX_DAYS, max(PEND_MIN_DAYS, int(interval_days * PEND_FRACTION)))


def days_left(last_done: date, interval_days: int, today: date) -> int:
    return (last_done + timedelta(days=interval_days) - today).days


def state(left: int, interval_days: int) -> str:
    if left < 0:
        return "PERM" if -left >= max(interval_days, PERM_MIN_DAYS) else "CONF"
    if left < pend_window(interval_days):
        return "PEND"
    return "OK"


def status_text(left: int) -> str:
    if left < 0:
        return f"Overdue {-left} d"
    if left == 0:
        return "Due today"
    return f"Due in {left} d"


def is_overdue(st: str) -> bool:
    return st in ("CONF", "PERM")


@dataclass(frozen=True)
class Code:
    code: str
    name: str
    description: str
    interval_days: int
    last_done: date
    days_left: int
    state: str
    snoozed: bool

    @property
    def zone(self) -> str:
        return self.code[0]

    @property
    def zone_name(self) -> str:
        return ZONES[self.zone]

    @property
    def category(self) -> int:
        return int(self.code[1])

    @property
    def status(self) -> str:
        return status_text(self.days_left)

    @property
    def active(self) -> bool:
        """Shown in Read codes: due or overdue, and not snoozed by Erase codes."""
        return self.state != "OK" and not self.snoozed


def evaluate(
    code: str,
    name: str,
    interval_days: int,
    last_done: date,
    snoozed_until: datetime | None,
    today: date,
    now: datetime,
    description: str = "",
) -> Code:
    left = days_left(last_done, interval_days, today)
    return Code(
        code=code,
        name=name,
        description=description,
        interval_days=interval_days,
        last_done=last_done,
        days_left=left,
        state=state(left, interval_days),
        snoozed=snoozed_until is not None and snoozed_until > now,
    )


def active_codes(codes: list[Code]) -> list[Code]:
    """Read codes order: worst state first, then most overdue first."""
    return sorted((c for c in codes if c.active), key=lambda c: (STATE_RANK[c.state], c.days_left))


def erasable(codes: list[Code]) -> list[Code]:
    return [c for c in active_codes(codes) if c.state != "PERM"]


def overdue_count(codes: list[Code]) -> int:
    return sum(is_overdue(c.state) for c in codes)


def health(codes: list[Code]) -> int:
    """Share of tracked chores not overdue. Snoozing doesn't help: the chores still wait."""
    if not codes:
        return 100
    return round(100 * (len(codes) - overdue_count(codes)) / len(codes))


def lamp_on(codes: list[Code]) -> bool:
    return any(is_overdue(c.state) and not c.snoozed for c in codes)


def readiness(codes: list[Code]) -> dict[str, str]:
    """Per zone letter: INC if any code there is overdue or snoozed, else RDY."""
    return {
        z: "INC" if any(c.zone == z and (is_overdue(c.state) or c.snoozed) for c in codes) else "RDY"
        for z in ZONES
    }


def service_due(codes: list[Code]) -> list[Code]:
    return sorted((c for c in codes if c.category == 2), key=lambda c: c.days_left)


def current_streak(counts: dict[date, int], end: date) -> int:
    """Consecutive zero-overdue days ending on `end`. A missing day (Pi off) breaks the run."""
    n, d = 0, end
    while counts.get(d) == 0:
        n += 1
        d -= timedelta(days=1)
    return n


def best_streak(counts: dict[date, int]) -> int:
    best, run, prev = 0, 0, None
    for d in sorted(counts):
        if counts[d] == 0:
            run = run + 1 if prev is not None and d - prev == timedelta(days=1) and counts[prev] == 0 else 1
            best = max(best, run)
        prev = d
    return best


def streaks(history: dict[date, int], today: date, overdue_today: int) -> tuple[int, int]:
    """(current, best) streaks. `history` maps local dates to the last recorded overdue count
    for that day; today's live count overrides any record."""
    counts = dict(history)
    counts[today] = overdue_today
    return current_streak(counts, today), best_streak(counts)
