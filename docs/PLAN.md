# homeOBD — Plan

## Goal

A self-hosted dashboard for apartment chores that looks and works like a handheld OBD scan
tool ("APT-OBD"). It runs on a Raspberry Pi 4 and is reachable **only on the home network**
(no public internet exposure). Phase 1 is a proof of concept with common household chores.
Later phases add IoT sensors that feed the same dashboard.

The design reference is the prototype in [`prototype/`](../prototype/README.md);
`prototype/template.html` holds its markup, screen logic and mock data.

## The scan-tool UI (from the prototype)

A single device-shaped panel: header "APT-OBD · Maintenance scanner", a pixel-font screen
with a title bar and a **CHK APT** warning lamp, a footer of key hints, and four buttons:
**▲**, **▼**, **ENTER**, **EXIT**. Rows on the screen can also be tapped directly.

Screen colour themes: **classic** (blue on light grey), **amber** (amber on black),
**green** (LCD green). Fonts: **Chakra Petch** 500/600 for the device body and **VT323** for
the screen.

| Screen        | Shows / does                                                                                 |
|---------------|----------------------------------------------------------------------------------------------|
| Boot          | "Software v1.0 / Linking to unit APT-01" with a progress bar; ENTER skips.                   |
| Diagnostic menu | The seven entries below; "Read codes" shows the active-code count.                       |
| Read codes    | Active codes, worst first (PERM → CONF → PEND). ENTER → detail → "Mark done?" → cleared.     |
| Code detail   | Zone, state, status ("Overdue 3 d" / "Due in 1 d"), interval, last done.                     |
| Erase codes   | Snoozes every active code that is not PERM for 24 h. Health is unchanged: the chores still wait. |
| Live data     | Health %, overdue codes, pending codes, lamp ON/OFF, streak, best streak, next service, tasks tracked. |
| Freeze frame  | Per code: when it went overdue, health and streak at that moment, last done, interval.        |
| Readiness     | Each zone RDY or INC, plus "N of 6 zones ready".                                             |
| Service due   | Maintenance items (category 2) sorted by days left; overdue shows "OVR n d".                 |
| Unit info     | Unit ID, software version, ECU (Raspberry Pi 4), interface (Web, Wi-Fi), zone and task counts. |

Adding and editing chores needs text entry, which four buttons can't do well, so it goes on a
separate plain **Setup page** (`/setup`). The theme is also chosen there.

## Codes, zones and states

**Code format:** zone letter + 4 digits, e.g. `K2002`.

| Zone letter | Zone      |
|-------------|-----------|
| K           | Kitchen   |
| B           | Bath      |
| L           | Living    |
| R           | Bedroom   |
| U           | Utility   |
| G           | Whole apt |

**First digit = category** (like OBD's generic vs. manufacturer codes):

| Digit | Category                                   | Typical interval |
|-------|--------------------------------------------|------------------|
| 0     | Routine cleaning                           | 1–7 days         |
| 1     | Periodic / deep cleaning                   | 1–8 weeks        |
| 2     | Maintenance & service (filters, safety…)   | 1–12 months      |
| 3     | Sensor-raised (reserved for Phase 2)       | —                |

The last three digits are a sequence number within the zone and category; gaps are fine.

**States.** Computed on every request from `last_done_at + interval_days` (in local calendar
days), never stored, so they can't drift:

| State | Meaning   | Rule (constants in `app/engine.py`)                               |
|-------|-----------|-------------------------------------------------------------------|
| —     | OK        | Not due yet; not shown in Read codes.                             |
| PEND  | Pending   | Days left < `min(7, max(1, ⌊15% of interval⌋))`; always on the due day. |
| CONF  | Confirmed | Overdue.                                                          |
| PERM  | Permanent | Overdue by at least `max(interval, 7)` days. Can't be erased.     |

**Derived values**

- **CHK APT lamp:** on while any CONF or PERM code is active and not snoozed.
- **Health %:** share of tracked chores that are not overdue (CONF/PERM), counted whether or
  not they are snoozed.
- **Streak:** consecutive days that ended with zero overdue codes; **best streak** is the record.
- **Readiness:** a zone is INC if it has any overdue or snoozed code, otherwise RDY.
- **Erase codes:** sets `snoozed_until = now + 24 h` on active non-PERM codes. They return after
  24 h if still not done. Marking a chore done clears its snooze.
- **Freeze frame:** captured when a code is first seen overdue: date, health at that moment and
  the streak it broke (the run up to yesterday). Cleared when the chore is marked done.

## Architecture (Phase 1)

```
 Phone / laptop on home Wi-Fi
            │  http://<pi-hostname>.local:8000
            ▼
 ┌─────────────────────── Raspberry Pi ───────────────────────┐
 │ systemd: homeobd.service                                    │
 │   uvicorn → FastAPI app                                     │
 │     ├── /            scan-tool UI (static HTML/CSS/JS)      │
 │     ├── /setup       add / edit chores, choose theme        │
 │     ├── /api/...     JSON API                               │
 │     └── background tick (every 5 min): freeze frames,       │
 │         daily health record for streaks                     │
 │   SQLite file: data/homeobd.db                              │
 └─────────────────────────────────────────────────────────────┘
```

**Why this stack**

- **Python + FastAPI:** light enough for a 1 GB Pi, and Python has the best Pi/IoT ecosystem
  for Phase 2 (`gpiozero`, `paho-mqtt`, sensor libraries).
- **SQLite:** zero-ops, a single file, trivially backed up. Plenty for one household.
- **Plain HTML/CSS/JS frontend:** the prototype's screen logic is a small state machine
  (`view()` in `template.html`), so it ports to vanilla JS without React or a build step.
- **Self-hosted fonts:** the Chakra Petch and VT323 `.woff2` files packed in the prototype
  export are extracted into `app/static/fonts/` with their OFL licence, so the UI works with no
  internet connection.
- **No Docker:** not worth the RAM and complexity for one service on a 1 GB board.

**Network scope (LAN only)**

- Bind to the Pi's LAN interface; reach it at `http://<hostname>.local:8000` (mDNS via
  `avahi-daemon`, i.e. `http://photostorage.local:8000`) or the Pi's IP. Give the Pi a DHCP reservation on the router.
- No port forwarding, TLS, public DNS or login for the POC: anyone on the home Wi-Fi can use it.
  Optional hardening: a firewall rule allowing port 8000 only from the local subnet.

**Time zone:** the Pi's clock is currently UTC. Set it to the local zone (`dietpi-config` →
Localisation, or `timedatectl set-timezone <Region/City>`) so "due today" and streak days
roll over at local midnight.

## Data model (Phase 1)

```
chores         (id, code UNIQUE, zone, name, description,
                interval_days, last_done_at, snoozed_until,
                trigger_type DEFAULT 'schedule',      -- 'sensor' reserved for Phase 2
                created_at)
completions    (id, chore_id, done_at, note)
freeze_frames  (id, chore_id, set_at, health_at_set, streak_at_set, cleared_at)
daily_health   (date PK, health, overdue_count)       -- powers streak / best streak
settings       (key PK, value)                        -- unit_id, theme
```

Zones are fixed (`engine.ZONES`) and a chore's zone is the first letter of its code, so there is
no zones table.

## API (Phase 1)

| Method | Path                         | Purpose                                                |
|--------|------------------------------|--------------------------------------------------------|
| GET    | `/api/codes`                 | Active codes (PEND/CONF/PERM) with status text, worst first |
| GET    | `/api/codes/{code}`          | One code's detail                                      |
| POST   | `/api/codes/{code}/done`     | Mark done ("clear code"): logs completion, clears snooze and freeze frame |
| POST   | `/api/codes/erase`           | Snooze active non-PERM codes for 24 h                  |
| GET    | `/api/codes/{code}/freeze`   | Freeze frame for a code                                |
| GET    | `/api/live`                  | Health, counts, lamp, streak, best streak, next service |
| GET    | `/api/readiness`             | RDY/INC per zone                                       |
| GET    | `/api/service`               | Category-2 items with days left                        |
| GET    | `/api/unit`                  | Unit info                                              |
| GET    | `/api/chores`                | All chores, including OK ones (Setup page)             |
| POST   | `/api/chores`                | Add a chore: give a `code`, or a `zone` + `category` to get the next free code |
| PATCH  | `/api/chores/{code}`         | Edit name / interval / zone                            |
| DELETE | `/api/chores/{code}`         | Remove a chore                                         |
| GET/PUT| `/api/settings`              | Theme, unit ID                                         |
| GET    | `/api/meta`                  | Zones, categories and themes (feeds the Setup page's menus) |

## Seed chores (18, matching the prototype's "Tasks tracked 18")

Codes marked ★ come straight from the prototype.

| Code     | Chore                        | Interval |
|----------|------------------------------|----------|
| K0001 ★  | Wash dishes                  | 1 d      |
| K0002    | Wipe counters & stovetop     | 2 d      |
| K0003    | Take out trash & recycling   | 3 d      |
| K1001    | Clean fridge interior        | 30 d     |
| K2001    | Degrease range-hood filter   | 90 d     |
| K2002 ★  | Clean fridge coils           | 180 d    |
| K2003 ★  | Descale kettle               | 30 d     |
| B0001    | Clean toilet & sink          | 7 d      |
| B1004 ★  | Scrub shower                 | 14 d     |
| B2001 ★  | Clean bath fan               | 60 d     |
| L0002 ★  | Vacuum living room           | 7 d      |
| L1001    | Dust surfaces                | 14 d     |
| R0001    | Vacuum bedroom               | 7 d      |
| R1001    | Change bed sheets            | 14 d     |
| U1001    | Run washer cleaning cycle    | 30 d     |
| U2001 ★  | Replace HVAC filter          | 90 d     |
| G0001    | Water plants                 | 4 d      |
| G2001 ★  | Test smoke alarms            | 180 d    |

## Milestones

### M0 — Setup ✅
- Git installed on the Pi and repo cloned to `/root/homeOBD`; repo-local git identity set.
- GitHub deploy key (write access) at `~/.ssh/homeobd_github`; remote uses SSH.
- SFTP enabled for Dropbear (`openssh-sftp-server`).
- `CLAUDE.md`, this plan and the prototype added.

### M1 — Backend ✅
- `app/` package: FastAPI app, SQLite schema created on startup, seed data, the API above.
- State engine as plain functions (state, status text, health, streak, readiness), separate
  from the web layer so it's easy to test and to reuse for sensor rules later.
- Background tick for freeze frames and the daily health record.
- Python venv in `.venv/`, `requirements.txt` (fastapi, uvicorn).
- `pytest` tests: state boundaries (PEND/CONF/PERM edges), erase/snooze expiry, health,
  streaks, freeze-frame capture and clearing, API happy paths.
- **Done when:** `curl localhost:8000/api/codes` returns seeded codes with correct states.

Run locally:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000   # API docs at /docs
```

The database lives in `data/homeobd.db` (override with `HOMEOBD_DB`) and is created and seeded on
first start.

### M2 — Scan-tool frontend ✅
- Recreate `prototype/template.html` in `app/static/`: the same layout, the three themes, all
  ten screens, ▲/▼/ENTER/EXIT and tap-to-select rows. Mock data replaced by `fetch('/api/...')`.
- Keyboard support: arrow keys, Enter, Escape.
- Fonts extracted from the export into `app/static/fonts/` with the OFL licence.
- `/setup` page: list, add, edit, delete chores; theme picker.
- **Done when:** from your phone you can read codes, mark one done and see the CHK APT lamp go out.

Files: `app/static/index.html` + `scantool.js` + `scantool.css` (scanner, served at `/`),
`setup.html` + `setup.js` + `setup.css` (served at `/setup`), `fonts.css` + `fonts/`. The
scanner re-reads its data every 60 s and whenever the tab becomes visible again.

### M3 — Run it on the Pi for real
- [ ] Set the Pi's time zone.
- [x] `deploy/homeobd.service`: starts on boot, restarts 3 s after a crash. Runs as root
  (the repo is in `/root`) with systemd sandboxing: everything read-only except `data/`.
  Access log is off to keep the RAM journal quiet.
- [x] `avahi-daemon` installed: the app is at `http://photostorage.local:8000`.
- [ ] DHCP reservation for the Pi (`192.168.0.157`) on the router (do this in the router's admin page).
- [x] Nightly backup: `deploy/backup.sh` via `homeobd-backup.timer` at 03:30 (or soon after boot
  if the Pi was off). Uses SQLite's online `.backup`, checks integrity, keeps the newest 14
  in `backups/` (not in git). Backups are on the same SD card; copying them off the Pi is a
  later improvement.
- **Done when:** the Pi reboots and the dashboard comes back on its own.

Install or update after pulling changes:

```bash
sudo ./deploy/install.sh
```

Useful commands: `systemctl status homeobd`, `journalctl -u homeobd -f`,
`systemctl list-timers homeobd-backup.timer`, `./deploy/backup.sh` (back up now).
To restore: `systemctl stop homeobd`, copy a backup over `data/homeobd.db` (and delete
`data/homeobd.db-wal` and `-shm`), then `systemctl start homeobd`.

### M4 — POC polish (optional)
- PWA manifest and icon so it can be added to the phone home screen.
- Completion history per code.
- LAN notifications for new CONF/PERM codes (e.g. self-hosted `ntfy` on the Pi).

## Phase 2 — IoT (later, design only for now)

- **Message bus:** Mosquitto MQTT broker on the Pi (LAN only). Sensors publish to
  `homeobd/<zone>/<sensor>/<metric>`.
- **Sensors:** ESP32/ESP8266 boards (ESPHome or MicroPython) or GPIO sensors on the Pi:
  temperature/humidity (bathroom mould risk), water leak (under the sink), door contact
  (fridge left open), power monitoring (appliance cycles), air quality.
- **Ingest service:** a small Python MQTT subscriber stores readings in a `readings` table and
  evaluates rules, e.g. "bathroom humidity > 70% for 2 h → raise `B3001` Ventilate bathroom".
  Sensor-raised chores use category 3 and `trigger_type = 'sensor'`.
- **Live data screen:** gains real sensor values, like OBD live PIDs.
- Revisit storage if reading volume grows (SQLite with retention first; a time-series DB only
  if needed).

## Working agreements

- Small, reviewable steps; each milestone ends with a working app on the Pi.
- Claude asks before committing significant changes (see `CLAUDE.md`).
