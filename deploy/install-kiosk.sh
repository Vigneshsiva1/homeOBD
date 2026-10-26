#!/bin/sh
# Show the scan tool on the Pi's 3.5" SPI touch panel (ILI9486 display + XPT2046 touch).
# Safe to re-run. See docs/PANEL.md. Reboot once afterwards if it changed the overlay.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CONFIG=/boot/firmware/config.txt
# fbtft driver, portrait. The kernel's DRM driver for this panel (piscreen,drm) leaves the
# goodtft/MPI3501-type boards white, so the kiosk runs X on the framebuffer instead.
OVERLAY='dtoverlay=piscreen,speed=16000000,rotate=180'

# X on the framebuffer, a window manager that keeps the one window full screen, and surf
# (a small WebKitGTK browser).
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    xserver-xorg-core xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit \
    matchbox-window-manager surf fonts-dejavu-core

if ! grep -qx "$OVERLAY" "$CONFIG"; then
    [ -e "$CONFIG.bak-homeobd" ] || cp "$CONFIG" "$CONFIG.bak-homeobd"
    if grep -q '^dtoverlay=piscreen' "$CONFIG"; then
        sed -i "s/^dtoverlay=piscreen.*/$OVERLAY/" "$CONFIG"
    else
        printf '\n#-------homeOBD 3.5in touch panel (docs/PANEL.md)-------\n%s\n' "$OVERLAY" >> "$CONFIG"
    fi
    echo "Set the panel overlay in $CONFIG: reboot to load it."
fi

id kiosk >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin kiosk

install -m 644 "$ROOT/deploy/99-homeobd-panel.rules" /etc/udev/rules.d/
udevadm control --reload
udevadm trigger --subsystem-match=graphics --subsystem-match=input
udevadm settle

install -m 644 "$ROOT/deploy/xorg-panel.conf" /etc/X11/homeobd-panel.conf
install -m 644 "$ROOT/deploy/homeobd-kiosk.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable homeobd-kiosk.service
systemctl restart homeobd-kiosk.service || true

systemctl --no-pager --lines=0 status homeobd-kiosk.service || true
