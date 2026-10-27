# The Pi's 3.5" touch panel

The scan tool also runs full screen on a 3.5" SPI display plugged onto the Pi's GPIO header,
in addition to the website: the panel is just another client of the same app. It opens
`http://127.0.0.1:8000/?panel`, and phones and laptops keep working as before.

The panel here is the common "3.5inch RPi Display": ILI9486 display controller behind a
16-bit shift register, XPT2046 resistive touch, 480 x 320, sitting on GPIO pins 1-26. It is
the goodtft / LCDwiki MPI3501 type (Waveshare 3.5" (A) clones have the same wiring).

## How it fits together

```
 GPIO header (SPI0)
   CE0 + GPIO24 (DC) + GPIO25 (reset) ──► fbtft ili9486 driver ──► /dev/fb-panel (320 x 480)
   CE1 + GPIO17 (pen down)            ──► ads7846 driver       ──► /dev/input (touch)
                                                    │
 systemd: homeobd-kiosk.service (always up)          ▼
   xinit ── Xorg (root, fbdev driver, tty7, no cursor)
        └── deploy/kiosk-session.sh: matchbox-window-manager, as user kiosk
                                                             (keeps the one window full screen)
 systemd: homeobd-panel-ui.service (only while the panel is on)
   surf (WebKitGTK browser, user kiosk) ──► http://127.0.0.1:8000/?panel

 systemd: homeobd-panel-power.service ── deploy/panel-power.py (root)
   reads the touchscreen and /api/codes; starts and stops homeobd-panel-ui;
   draws black / the splash straight into /dev/fb-panel
```

- **Driver:** the kernel's own `piscreen` overlay, fbtft mode. It has this panel's wiring
  and init sequence. No vendor `LCD-show` scripts: they replace system config files.
- **Why not the DRM driver:** `piscreen,drm` (the kernel's `ili9486` DRM driver) loads without
  errors but leaves this board white, at 16 MHz and at 4 MHz. Without DRM there is no Wayland
  kiosk (cage + cog would have used about 190 MB), so it is X on the framebuffer: about
  300 MB for X, surf and its WebKit processes.
- **`?panel`:** drops the device body, cable and Setup link so the scanner screen fills the
  panel, and shortens the footer so the whole menu fits. Setup needs a keyboard, so chores
  are still added from a phone or laptop. The webpage itself is unchanged.

## On and off

The panel is off most of the time, and so is its browser: `deploy/panel-power.py` only runs
`homeobd-panel-ui.service` while the panel is on. The homeOBD backend and the website don't
change; only the panel's own interface starts and stops.

- **Tap the panel** while it is black: it shows an `APT-OBD / LINKING...` splash at once,
  then the menu once the browser has started (about 10 s, most of it WebKit starting; a white
  blink shows just before the menu). The waking tap does nothing else.
- **A new code, or a code that gets worse** (PEND -> CONF -> PERM), turns it on for 30 s,
  checked once a minute. Codes set between 22:00 and 08:00 wait until 08:00, so the daily
  codes set at midnight don't light the room at night.
- **Off** after 60 s without a tap: the browser stops and the panel is drawn black.
- It also comes on for 30 s when the service starts (boot), to show the panel works.

Off, the kiosk uses about 60 MB (X ~30, matchbox ~7, the daemon ~22) instead of about 560 MB.
Black is as dark as it gets: the backlight is wired always-on (see Brightness), so it still
glows faintly and draws its power; only the Pi's CPU, memory and SPI traffic are saved.
The times are constants at the top of `deploy/panel-power.py` (`IDLE_OFF`, `CODE_WAKE`,
`QUIET`, `POLL`). On the panel, the scan tool skips its boot progress bar and waits for its
font, so the menu is the first and only picture the browser draws.

## Panel controls

The panel can't scroll smoothly (see Speed), so it works with buttons instead of swipes:

- Tap a row to open it, **‹ Back** to go back, as on the phone.
- Screens longer than one page get **▲** / **▼** at the ends of the footer: one tap turns a
  whole page (one redraw). A page starts with the first row the page before cut off; the
  buttons dim on the first and last page. Swiping does nothing.
- A screen is drawn once, with its data (it waits up to 250 ms for the API instead of first
  drawing "Reading..."), and the 60 s refresh skips redraws that would change nothing.

All of this is in `scantool.js` behind `PANEL` (`turnPage`, `pageStarts`, `go`) and in the
`.panel` / `.pager` styles; without `?panel` the page behaves as before.

## Install

```bash
sh deploy/install-kiosk.sh
```

It installs `xserver-xorg-core xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit
matchbox-window-manager surf`, sets this line in `/boot/firmware/config.txt` (the first run
keeps a copy in `config.txt.bak-homeobd`), creates the `kiosk` user, the udev rule, the X
config (`/etc/X11/homeobd-panel.conf`), a black GTK background for the browser (no white
window while it starts) and the three services; it enables `homeobd-kiosk` and
`homeobd-panel-power`. Reboot once if it changed the line.

```
dtoverlay=piscreen,speed=16000000,rotate=180
```

## Settings

- **Orientation:** `rotate=180` is portrait the right way up for this panel on this Pi;
  `rotate=0` is upside down. The UI is built for portrait (320 x 480). Changing the rotation
  means calibrating touch again.
- **Speed:** 16 MHz SPI. A full screen is 300 KiB and takes about 0.33 s to send (measured;
  the driver sends 4 KiB chunks, and a bigger `txbuflen` hangs it). 32 MHz was tried on
  2026-10-26: 0.22 s a screen, but stripes showed while the screen changed, so it is back at
  16 MHz. surf repaints the whole window on every touch event, even on a blank page, so a tap
  costs about two full redraws (press, then release with the new screen) whatever the page
  does.
- **Brightness:** the backlight is wired always-on (the overlay's GPIO22 "led" switch does
  nothing on this board), so `dim=75` in `deploy/homeobd-panel-ui.service` darkens the theme's colours
  to 75 % instead (`?dim=75`, `dimColours` in `scantool.js`). 100 = as on the phone. A CSS
  `filter: brightness()` looks the same but costs a second redraw per change.
- **Touch:** `deploy/99-homeobd-panel.rules` holds the libinput calibration matrix (axes
  swapped and both flipped for `rotate=180`). To redo it: `python3 deploy/calibrate-touch.py
  --write`. It stops the kiosk, draws five crosshairs on the panel one at a time (tap each
  centre, a fingernail works best), fits the matrix, prints how far off each tap lands,
  saves and applies it, and restarts the kiosk. The 2026-10-26 fit lands within 5 px.
- **Framebuffer name:** the panel is `fb0`, or `fb1` when HDMI is plugged in at boot, so the
  udev rule adds `/dev/fb-panel` and the service passes the real path to X as `FRAMEBUFFER`
  (the fbdev driver won't open the symlink).

## Troubleshooting

```bash
systemctl status homeobd-kiosk homeobd-panel-power homeobd-panel-ui
journalctl -u homeobd-kiosk -u homeobd-panel-power -u homeobd-panel-ui -b
grep EE /var/log/Xorg.0.log
```

- White screen: the overlay isn't loaded (`dtoverlay -l`, `ls -l /dev/fb-panel`), or it is
  the DRM variant (`drm` in the overlay line).
- Taps land in the wrong place: calibrate again (above).
- The `MESA-EGL ... Permission denied` lines in the journal are harmless: WebKit draws in
  software because the framebuffer has no GPU.
- Black and a tap does nothing: `homeobd-panel-power` isn't running, or the touchscreen
  isn't found (its journal says so).
- The panel stops updating for a few seconds now and then: memory. While on, the kiosk takes about
  560 MB (WebKit ~270, surf ~150, network process ~70, X ~60) of the Pi's 905 MB, and a Claude
  Code session on the Pi another ~260 MB. With no swap, the kernel then drops program code
  and reads it back from the SD card (`workingset_refault_file` in `/proc/vmstat` climbs).
  The page's own state keeps going; only painting stalls.
