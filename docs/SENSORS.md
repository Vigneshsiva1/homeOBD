# homeOBD — Phase 2: ESP32 sensors (hand-off)

Context for starting the sensor phase in a fresh session. Read `CLAUDE.md` first (rules,
precedence, UI rules), then this file. `docs/PLAN.md` has the full Phase 1 design.

## Where things stand (2026-10-26)

Phase 1 is done and in daily use; the user is happy with the UI and chores.

- **Running:** FastAPI + SQLite on the Pi 4 (DietPi), systemd `homeobd.service`, nightly DB
  backup at 03:30. LAN `http://192.168.0.157:8000`, tailnet HTTPS
  `https://photostorage.tail82999e.ts.net` via `tailscale serve` (never Funnel).
- **App:** iPhone home-screen web app (PWA), touch-only scan-tool UI, iOS conventions, fills the
  iPhone 17 screen (see the `fitScreen()` note in `CLAUDE.md`). Help has guide topics plus every
  chore with steps, DONE WHEN, next due date, minutes, and drawn plant pictures.
- **Chores:** 48 real chores in the live DB (data, not in git; nightly backups only). Each has
  `how_to`, `done_when`, `minutes`. Plants run on "check soil" schedules (G0001 celosia,
  G0002 mint, G0003 Chinese money plant, G0004 umbrella plant, G0005 palm, G0006 bird of paradise).
- **Notifications:** Web Push from the app (pywebpush, VAPID keys on the Pi). Slots: quick chores
  (every 1–2 d, under 1 h) at 20:00; other chores under 1 h at 08:00 plus 18:00 on weekdays;
  chores of 1 h+ only Sat/Sun at 08:00 and 18:00. One iPhone subscribed and confirmed working.
- **Code:** `app/engine.py` (pure rules), `app/service.py` (DB + engine), `app/push.py`,
  `app/api.py`, `app/main.py` (5-minute tick), `app/static/` (UI). 87 pytest tests.
- **Still open from Phase 1.5 picks:** completion history per code (F02), seasonal intervals
  (F04), freeze-frame "Set on" = actual overdue date (D10). No off-Pi backup copy (user's choice).

## Decisions already made (Phase 2 worksheet, 2026-10-26)

| | Decision |
|---|---|
| Platform | **ESP32 boards with ESPHome** over Wi-Fi. The user has a few **ESP32-C3** and **ESP32-S3** boards. No Zigbee. |
| Appliances | **Switched by hand.** homeOBD raises a code ("Turn on dehumidifier"); no IR blaster, no smart plugs. |
| Rules | Live **inside homeOBD**, not Home Assistant. |
| Outdoor air | **Yes**, from Open-Meteo (outgoing request only). |
| Plants | Schedules stay; soil sensors were also picked, so add sensors on top (start with the fussiest plant). |
| Hosting | Stays on the Pi. |

Routines picked (worksheet IDs): **R01** bathroom humidity > 70 % for 30 min → "Ventilate
bathroom"; **R02** humidity > 55 % → "Turn on dehumidifier" (off at 50 %); **R03** humidity < 35 %
→ "Turn on humidifier" (off at 40 %); **R04** CO₂ > 1000 ppm and outside air good → "Open
windows"; **R05** outdoor AQI > 100 → "Close windows" + "Run purifier"; **R06** PM2.5 > 12 µg/m³ →
"Run purifier" (high above 35); **R09** humidifier run-time → "Clean and refill humidifier";
**R10** leak → urgent code; **R12** soil dry → "Water <plant>"; **R13** homeserver unreachable → code.
Not picked: R07 (bucket full via power plug), R08 (filter by run-time), R11 (fridge temperature).

**Resolve before building:**
- R13 conflicts with D11 ("don't show homeserver status in homeOBD"). Ask which wins.
- R09 needs appliance run-time, which needs a power-metering plug (not picked). Either infer
  from humidity, keep it as a schedule chore, or drop it. Ask.

## Shopping list (sensors picked: S01, S02, S03, S07, S08)

Adafruit/DFRobot parts are genuine and mostly solderless (STEMMA QT plugs). AliExpress clones
cost less but quality varies, especially for CO₂ sensors. Prices are from listings seen
2026-10-26; check before buying.

| Qty | Part | Measures | Link | Approx. |
|---|---|---|---|---|
| 2–3 | **Adafruit SHT41** (STEMMA QT) | Temperature, humidity | https://www.adafruit.com/product/5776 | $5.95 each |
| 1 | **Adafruit PM2.5 sensor kit, PMS5003** | PM1 / PM2.5 / PM10 | https://www.adafruit.com/product/3686 | $39.95 |
| 1 | **CO₂, choose one:** Adafruit **SCD-40** (I²C, plug-in, also gives temp/humidity) | True CO₂ 400–2000 ppm | https://www.adafruit.com/product/5187 | see page |
| | …or **Senseair S8** 004-0-0013 (UART, 5 V, cheaper, clone risk elsewhere) | CO₂ 400–2000 ppm | https://www.digikey.ie/en/products/detail/senseair/004-0-0013/10416534 (same part on digikey.com) | ~€34 |
| 1–4 | **DFRobot SEN0308** waterproof capacitive soil sensor (SEN0193 is retired) | Soil moisture | https://wiki.dfrobot.com/SEN0308 · retail: https://ca.robotshop.com/products/dfrobot-gravity-analog-waterproof-capacitive-soil-moisture-sensor | see page |
| 2–4 | **STEMMA QT to female-socket cable, 150 mm** (for SHT41/SCD-40 to ESP32 pins) | — | https://www.adafruit.com/product/4397 | $0.95 each |
| 2 | **Leak probes**: two bare wires or a pair of screws per sink, no module needed | Water on the floor | ESPHome cookbook: https://esphome.io/cookbook/leak-detector-m5stickC | ~$0 |

If the bedroom gets an SCD-40 it also reports temperature and humidity, so only 2 SHT41s are
needed (bathroom, living room).

## Proposed build (to confirm with the user)

| Node | Board | Sensors | Feeds rules |
|---|---|---|---|
| Bathroom | ESP32-C3 | SHT41 (I²C) + leak probe under the sink (GPIO input with pull-up) | R01, R02/R03, R10 |
| Bedroom | ESP32-C3 or S3 | SCD-40 (I²C) or S8 (UART, powered from 5 V) | R04, R02/R03 |
| Living room | ESP32-S3 | SHT41 (I²C) + PMS5003 (UART, 5 V power, 3.3 V logic) | R02/R03, R06 |
| Plant shelf | ESP32-S3 | SEN0308 soil sensors on ADC1 pins (one per pot) | R12 |
| Kitchen sink | ESP32-C3 | leak probe | R10 |

Wiring notes: ESP32-C3 has **no capacitive touch pins** (use a digital input + 10 kΩ pull-up for
leak probes); ESP32-S3 has touch pins. Use **ADC1** pins for analog (ADC2 conflicts with Wi-Fi).
SEN0308 outputs about 0–2.9 V; calibrate dry/wet per pot. PMS5003 and Senseair S8 need 5 V power
(S8: 4.5–5.25 V, more damages it); their UART logic is 3.3 V-safe. All nodes powered by USB.

## Software architecture

```
 ESP32 nodes (ESPHome) ──Wi-Fi/MQTT──▶ Mosquitto on the Pi (LAN only, 1883, user/password)
                                            │
                    homeOBD ingest task (subscribes homeobd/#) ──▶ readings table
                                            │
     5-min tick: rules (engine, pure) ──▶ sensor codes in Read codes ──▶ Web Push (immediate)
     Open-Meteo (hourly) ──▶ outdoor AQI reading ─┘
```

- **Firmware:** ESPHome YAML per node, kept in the repo (e.g. `esphome/<node>.yaml`, secrets in a
  gitignored `esphome/secrets.yaml`). **Compile on the Mac** (`pip install esphome`), not the Pi
  (1 GB RAM); first flash over USB, then over the air. Use the `mqtt:` component with
  `topic_prefix: homeobd/<node>` so states land on `homeobd/<node>/sensor/<name>/state`.
- **Broker:** `apt install mosquitto`, bound to the LAN interface, password file, no Tailscale or
  internet exposure. Add it to `CLAUDE.md` host notes and `deploy/`.
- **Ingest:** an asyncio MQTT client inside the app process (e.g. `aiomqtt`; check the current
  version and that the systemd sandbox allows the connection) writing to a `readings` table
  (`node, metric, value, at`). Keep raw readings ~7 days; roll up to hourly averages after that.
  Mark a node offline if it stops reporting (good "check the sensor" code).
- **Rules:** pure functions in `engine.py` (`readings → active sensor alerts`), with hysteresis
  (on at 55 %, off at 50 %) and minimum durations (R01: 30 min) so codes don't flap. Test them like
  the chore rules, with fake readings.
- **Sensor codes:** category **3** codes (e.g. `B3001 Ventilate bathroom`), `trigger_type =
  'sensor'` (column already exists). They appear in Read codes, light CHK APT, and clear by
  themselves when the condition ends or when marked done. Decide the storage: an `alerts` table
  (code, since, cleared_at, value) merged into the code list is likely cleaner than faking
  interval chores.
- **Notifications:** sensor codes go out **immediately**, not in the chore slots, with a per-code
  cooldown (e.g. once per 2 h) and quiet hours 22:00–07:00 **except leaks**, which always notify.
- **Live data:** add per-room readings (temperature, humidity, CO₂, PM2.5, soil) under Live data
  or a new "Sensors" menu entry; follow the UI rules in `CLAUDE.md`.
- **Outdoor air:** Open-Meteo air-quality API (`us_aqi`, `pm2_5`) hourly for Chicago; needs the
  location (city-level is enough; ask the user).

## Suggested order

1. Mosquitto on the Pi + one bathroom node (C3 + SHT41) publishing; check with `mosquitto_sub`.
2. Ingest + `readings` table + a Sensors/Live data screen showing live values.
3. Rules engine + sensor codes + immediate notifications; start with R01 and R10.
4. Remaining nodes (bedroom CO₂, living PM2.5, plant shelf, kitchen leak) and their rules.
5. Open-Meteo outdoor AQI, then R04/R05.

Each step ends working on the Pi, with tests, and the user is asked before committing.
