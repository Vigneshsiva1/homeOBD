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
 systemd: homeobd-kiosk.service                     ▼
   xinit ── Xorg (root, fbdev driver, tty7, no cursor)
        └── deploy/kiosk-session.sh, as user kiosk:
              matchbox-window-manager (keeps the one window full screen)
              surf (WebKitGTK browser) ──► http://127.0.0.1:8000/?panel
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
config (`/etc/X11/homeobd-panel.conf`) and the service. Reboot once if it changed the line.

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
  nothing on this board), so `DIM=60` in `deploy/kiosk-session.sh` darkens the theme's colours
  to 60 % instead (`?dim=60`, `dimColours` in `scantool.js`). 100 = as on the phone. A CSS
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
systemctl status homeobd-kiosk
journalctl -u homeobd-kiosk -b
grep EE /var/log/Xorg.0.log
```

- White screen: the overlay isn't loaded (`dtoverlay -l`, `ls -l /dev/fb-panel`), or it is
  the DRM variant (`drm` in the overlay line).
- Taps land in the wrong place: calibrate again (above).
- The `MESA-EGL ... Permission denied` lines in the journal are harmless: WebKit draws in
  software because the framebuffer has no GPU.
- The panel stops updating for a few seconds now and then: memory. The kiosk takes about
  560 MB (WebKit ~270, surf ~150, network process ~70, X ~60) of the Pi's 905 MB, and a Claude
  Code session on the Pi another ~260 MB. With no swap, the kernel then drops program code
  and reads it back from the SD card (`workingset_refault_file` in `/proc/vmstat` climbs).
  The page's own state keeps going; only painting stalls.
