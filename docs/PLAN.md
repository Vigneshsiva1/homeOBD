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
with a title bar and a **CHK APT** warning lamp. Since 2026-10-26 it follows iOS conventions
(see the UI rules in `CLAUDE.md`): touch-only (the prototype's ▲/▼/ENTER/EXIT buttons are
gone), tap a row to open it, **‹ Back** at the left of the title bar, and a fixed-height footer
with iOS-style action buttons (**YES**/**NO**, **ERASE**/**CANCEL**, **CONTINUE**, **SKIP**) or
a hint. The device fills the whole phone screen, every screen is the same size, and long lists
scroll inside the screen. Setup is a gear link in the brand row. Arrow keys, Enter and Escape
still work on a computer.

Screen colour themes: **classic** (blue on light grey), **amber** (amber on black),
**green** (LCD green). Fonts: **Chakra Petch** 500/600 for the device body and **VT323** for
the screen.

| Screen        | Shows / does                                                                                 |
|---------------|----------------------------------------------------------------------------------------------|
| Boot          | "Software v1.0 / Linking to unit APT-01" with a progress bar; ENTER skips.                   |
| Diagnostic menu | The eight entries below; "Read codes" shows the active-code count.                       |
| Read codes    | Active codes, worst first (PERM → CONF → PEND). ENTER → detail → "Mark done?" → cleared.     |
| Code detail   | Zone, state, status ("Overdue 3 d" / "Due in 1 d"), interval, last done; rows **Mark done** and **Help**. |
| Code help     | From a code's detail: the chore's steps, then **DONE WHEN** (what finished looks like). The "Mark done?" screen repeats DONE WHEN. |
| Erase codes   | Snoozes every active code that is not PERM for 24 h. Health is unchanged: the chores still wait. |
| Live data     | Health %, overdue codes, pending codes, lamp ON/OFF, streak, best streak, next service, tasks tracked. |
| Freeze frame  | Per code: when it went overdue, health and streak at that moment, last done, interval.        |
| Readiness     | Each zone RDY or INC, plus "N of 6 zones ready".                                             |
| Service due   | Maintenance items (category 2) sorted by days left; overdue shows "OVR n d".                 |
| Unit info     | Unit ID, software version, ECU (Raspberry Pi 4), interface (Web, Wi-Fi), zone and task counts. |
| Help          | Guide topics first (daily use, add & edit chores, codes, lamp, notifications, each menu screen), then every chore with next due date, time, steps and DONE WHEN; plant chores show a drawn illustration (`app/static/pictures/`, no personal photos since the repo is public). |

Adding and editing chores needs text entry, which the scanner screen isn't built for, so it goes on a
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

- Also on the tailnet over HTTPS via `tailscale serve` (see M5); never Funnel.
- Bind to the Pi's LAN interface; reach it at `http://<hostname>.local:8000` (mDNS via
  `avahi-daemon`, i.e. `http://photostorage.local:8000`) or the Pi's IP. Give the Pi a DHCP reservation on the router.
- No port forwarding, TLS, public DNS or login for the POC: anyone on the home Wi-Fi can use it.
  Optional hardening: a firewall rule allowing port 8000 only from the local subnet.

**Time zone:** the Pi runs on `America/Chicago`, so "due today" and streak days roll over
at local midnight.

## Data model (Phase 1)

```
chores         (id, code UNIQUE, zone, name, description,
                how_to, done_when,                     -- Help screen: steps, finished state
                minutes,                               -- rough duration; picks notification times
                interval_days, last_done_at, snoozed_until,
                trigger_type DEFAULT 'schedule',      -- 'sensor' reserved for Phase 2
                created_at)
completions    (id, chore_id, done_at, note)
freeze_frames  (id, chore_id, set_at, health_at_set, streak_at_set, cleared_at)
daily_health   (date PK, health, overdue_count)       -- powers streak / best streak
settings       (key PK, value)                        -- unit_id, theme
push_keys      (id=1, private_pem, public_key)        -- this unit's VAPID keys, never via the API
push_subscriptions (endpoint UNIQUE, p256dh, auth, user_agent, created_at)
notify_log     (date, slot, sent_at, codes)           -- each notification slot handled once
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
| PATCH  | `/api/chores/{code}`         | Edit name, interval, last done, notes, help (`how_to`, `done_when`) |
| DELETE | `/api/chores/{code}`         | Remove a chore                                         |
| GET/PUT| `/api/settings`              | Theme, unit ID                                         |
| GET    | `/api/meta`                  | Zones, categories and themes (feeds the Setup page's menus) |
| GET    | `/api/push/key`              | VAPID public key for subscribing                        |
| POST   | `/api/push/subscribe` / `unsubscribe` | Add or remove this device's push subscription  |
| POST   | `/api/push/test`             | Send a test notification to every subscribed device     |
| GET    | `/api/push/status`           | Subscribed device count and slot times                  |

## Seed chores (18, matching the prototype's "Tasks tracked 18")

Used for a fresh database and by the tests. On the Pi this demo list was replaced on
2026-10-26 by the real list of 48 chores (each with help text) chosen in the Phase 2 worksheet.

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
- [x] Time zone set to `America/Chicago`.
- [x] `deploy/homeobd.service`: starts on boot, restarts 3 s after a crash. Runs as root
  (the repo is in `/root`) with systemd sandboxing: everything read-only except `data/`.
  Access log is off to keep the RAM journal quiet.
- [x] `avahi-daemon` installed: the app is at `http://photostorage.local:8000`.
- [x] No DHCP reservation for now: use the Pi's IP (`192.168.0.157`). If the router ever hands
  out a new one, `photostorage.local` still finds the Pi.
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

### M4 — Real chores and help ✅
- Chore help: `how_to` and `done_when` on every chore, shown under **Help** on the scanner and
  edited on the Setup page. Older databases gain the columns on startup.
- Chore list rebuilt from the worksheet picks: 48 chores, including one "check soil" chore per
  plant (celosia, mini trailing plant, Chinese money plant, umbrella plant, palm, bird of
  paradise) and a monthly plant care round. Demo last-done dates were reset to 2026-10-26.
- Fix: editing a chore's last-done date closes its open freeze frame.

### M5 — Next app features (picked 2026-10-26)
- Phone home-screen app: manifest (`/manifest.webmanifest`), icons in `app/static/icons/`,
  iPhone tags, and a network-first service worker (`/sw.js`) that keeps the app shell available
  when the Pi is unreachable (API calls are never cached). Served over HTTPS on the tailnet with
  `tailscale serve` → `https://photostorage.tail82999e.ts.net` (no Funnel). Add it from Chrome or
  Safari: Share → Add to Home Screen.
- Completion history per code.
- Phone notifications ✅ via Web Push from the home-screen app (chosen over ntfy on 2026-10-26).
  Each chore has an estimated `minutes`; the schedule (`engine.slot_codes`, `app/push.py`):
  quick chores (every 1-2 days, under 1 h) at **8 pm**; other chores under 1 h at **8 am** plus
  **6 pm** on weekdays; chores of 1 h or more only on **Saturday/Sunday at 8 am and 6 pm**. One
  notification per slot lists every active code in it; snoozed codes stay quiet; a slot missed
  while the Pi was off still fires up to 2 h late. Turned on per device on the Setup page.
- Seasonal intervals (e.g. plants and fertilizing less often in winter).
- Freeze frame "Set on" = the day the chore actually went overdue.
- Maybe: sensor readings on Live data (waits for Phase 2).

Decisions recorded: homeOBD stays on the Pi; no off-Pi copy of its backups; appliances are
switched by hand (homeOBD raises the code); automation rules live in homeOBD, not Home
Assistant; homeserver status stays out of homeOBD; plants run on schedules, not sensors.

## Phase 2 — IoT (on hold)

Picked but parked on 2026-10-26: ESP32 boards with ESPHome, outdoor air quality from
Open-Meteo, SHT41 ×3, PMS5003, Senseair S8/SCD40, soil sensors, leak probes; routines R01-R06,
R09, R10, R12, R13 from the worksheet.

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
