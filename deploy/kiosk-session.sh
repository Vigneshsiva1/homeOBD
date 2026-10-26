#!/bin/sh
# X session on the 3.5in panel, run by homeobd-kiosk.service through xinit. X runs as root
# (screen blanking is off in xorg-panel.conf); the window manager and browser run as the
# unprivileged kiosk user.
export HOME=/home/kiosk
# Software rendering only: the panel's framebuffer has no GPU behind it.
export WEBKIT_DISABLE_COMPOSITING_MODE=1
# Picture brightness in percent. The backlight itself is always fully on, so this darkens
# the colours instead; 100 = as on the phone.
DIM=60
runuser -u kiosk -- matchbox-window-manager -use_titlebar no -use_cursor no &
exec runuser -u kiosk -- surf -F "http://127.0.0.1:8000/?panel&dim=$DIM"
