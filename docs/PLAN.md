# homeOBD — Plan

## Goal

A self-hosted, OBD-style dashboard for apartment chores, running on a Raspberry Pi 4 and
reachable **only on the home network** (no public internet exposure). Phase 1 is a proof of
concept with a handful of common household chores. Later phases add IoT sensors that feed the
same dashboard.

## The OBD metaphor

| Car OBD              | homeOBD                                                        |
|----------------------|----------------------------------------------------------------|
| Diagnostic code      | Chore code, e.g. `KIT-01` (Kitchen), `BTH-02` (Bathroom)        |
| System OK            | Chore done within its interval                                 |
| Pending code         | Due soon (e.g. within 20% of the interval or 1 day)            |
| Check-engine light   | Overdue                                                        |
| Clear codes          | "Mark done" resets the timer and logs a completion             |
| Freeze-frame / log   | Completion history per chore                                   |
| Live sensor data     | Phase 2: real sensor readings (humidity, leaks, temperature…)  |

Status is always **computed** from `last_done_at + interval`, never stored, so it can't drift.

## Architecture (Phase 1)

```
 Phone / laptop on home Wi-Fi
            │  http://<pi-hostname>.local:8000
            ▼
 ┌─────────────────────── Raspberry Pi ───────────────────────┐
 │ systemd: homeobd.service                                    │
 │   uvicorn → FastAPI app                                     │
 │     ├── /            static HTML/CSS/JS (from prototype)    │
 │     └── /api/...     JSON API                               │
 │   SQLite file: data/homeobd.db                              │
 └─────────────────────────────────────────────────────────────┘
```

**Why this stack**

- **Python + FastAPI**: light enough for a 1 GB Pi, and Python has the best Pi/IoT ecosystem
  for Phase 2 (`gpiozero`, `paho-mqtt`, sensor libraries).
- **SQLite**: zero-ops, a single file, trivially backed up. Plenty for one household.
- **Plain HTML/CSS/JS frontend** adapted from the existing HTML prototype: no build step, no
  Node toolchain on the Pi. It fetches data from the API instead of hard-coding it.
- **No Docker**: not worth the RAM/complexity for one service on a 1 GB board.

**Network scope (LAN only)**

- Bind to the Pi's LAN interface; reach it at `http://<hostname>.local:8000` (mDNS via
  `avahi-daemon`) or the Pi's IP. Give the Pi a DHCP reservation on the router.
- No port forwarding, no TLS, no public DNS, no login for the POC: anyone on the home Wi-Fi
  can use it. Optional hardening: a firewall rule allowing port 8000 only from the local
  subnet (e.g. `192.168.1.0/24`).

## Data model (Phase 1)

```
areas        (id, code, name)                       -- KIT, BTH, LIV, BED, GEN
chores       (id, code, area_id, name, description,
              interval_days, last_done_at, created_at,
              trigger_type  DEFAULT 'schedule')     -- 'sensor' reserved for Phase 2
completions  (id, chore_id, done_at, note)
```

`trigger_type` is added now so sensor-raised chores in Phase 2 don't need a schema rewrite.

## API (Phase 1)

| Method | Path                           | Purpose                                   |
|--------|--------------------------------|-------------------------------------------|
| GET    | `/api/chores`                  | All chores with computed status + due date |
| POST   | `/api/chores`                  | Add a chore                               |
| PATCH  | `/api/chores/{id}`             | Edit name / interval / area               |
| DELETE | `/api/chores/{id}`             | Remove a chore                            |
| POST   | `/api/chores/{id}/complete`    | Mark done ("clear code"), logs completion |
| GET    | `/api/chores/{id}/history`     | Completion log                            |
| GET    | `/api/summary`                 | Counts by status + overall "health" score |

## Seed chores

| Code   | Chore                               | Interval |
|--------|-------------------------------------|----------|
| KIT-01 | Wipe counters & stovetop            | 2 days   |
| KIT-02 | Take out trash & recycling          | 3 days   |
| KIT-03 | Clean fridge, toss old food         | 30 days  |
| KIT-04 | Clean dishwasher filter             | 30 days  |
| KIT-05 | Degrease range-hood filter          | 90 days  |
| BTH-01 | Clean toilet, sink & mirror         | 7 days   |
| BTH-02 | Scrub shower / tub                  | 14 days  |
| LIV-01 | Vacuum / mop floors                 | 7 days   |
| LIV-02 | Dust surfaces                       | 14 days  |
| BED-01 | Change bed sheets                   | 14 days  |
| GEN-01 | Water plants                        | 4 days   |
| GEN-02 | Replace HVAC / air-purifier filter  | 90 days  |
| GEN-03 | Test smoke detector                 | 180 days |

## Milestones

### M0 — Setup ✅ (this session)
- Git installed on the Pi, repo cloned to `/root/homeOBD`, `CLAUDE.md` and this plan added.
- Still needed from you: a git identity on the Pi, push credentials for GitHub (a fine-grained
  personal access token or an SSH deploy key), and the HTML prototype file copied into the repo
  (e.g. `prototype/index.html`).

### M1 — Backend skeleton
- `app/` package: FastAPI app, SQLite schema + migrations-on-startup, seed data, the API above.
- Python venv in `.venv/`, `requirements.txt` (fastapi, uvicorn).
- `pytest` tests for status computation (OK / due soon / overdue edge cases) and the API.
- **Done when:** `curl localhost:8000/api/chores` returns the seeded chores with statuses.

### M2 — Dashboard frontend
- Port the prototype HTML into `app/static/`, replace hard-coded data with `fetch('/api/...')`.
- Cards per chore with code, status light, "due in / overdue by", and a **Mark done** button.
- Add/edit chore form; filter by area or status; overall health gauge.
- Mobile-first layout (it will mostly be used from a phone).
- **Done when:** you can mark a chore done from your phone and see it turn green.

### M3 — Run it on the Pi for real
- `deploy/homeobd.service` systemd unit (auto-start on boot, restart on crash).
- `avahi-daemon` so `http://<hostname>.local:8000` works; DHCP reservation on the router.
- Nightly SQLite backup (`sqlite3 .backup` via cron/systemd timer, keep the last 14).
- **Done when:** the Pi reboots and the dashboard comes back on its own.

### M4 — POC polish (optional)
- PWA manifest + icon so it can be "installed" to the phone home screen.
- Completion history view; simple streaks / stats.
- Optional LAN notifications for overdue chores (e.g. self-hosted `ntfy` on the Pi).

## Phase 2 — IoT (later, design-only for now)

- **Message bus:** Mosquitto MQTT broker on the Pi (LAN only). Sensors publish to
  `homeobd/<area>/<sensor>/<metric>`.
- **Sensors:** ESP32 / ESP8266 boards (ESPHome or MicroPython) or GPIO sensors on the Pi:
  temperature/humidity (bathroom mould risk), water-leak (under sink), door contact (fridge
  left open), power monitoring (dryer/dishwasher cycles), air quality.
- **Ingest service:** a small Python MQTT subscriber that stores readings in a `readings` table
  and evaluates rules, e.g. "bathroom humidity > 70% for 2 h → raise `BTH-03` Ventilate".
  Rule-raised chores use `trigger_type = 'sensor'`.
- **Dashboard:** a "live data" panel per area, mirroring OBD live PIDs.
- Revisit storage if reading volume grows (SQLite with retention first; a time-series DB only
  if needed).

## Working agreements

- Small, reviewable steps; each milestone ends with a working app on the Pi.
- Claude asks before committing significant changes (see `CLAUDE.md`).
