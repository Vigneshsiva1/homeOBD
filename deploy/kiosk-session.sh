#!/bin/sh
# X session on the 3.5in panel, run by homeobd-kiosk.service through xinit. X runs as root
# (screen blanking is off in xorg-panel.conf) and stays up; it only holds the window manager,
# run as the unprivileged kiosk user. The browser is homeobd-panel-ui.service, which
# deploy/panel-power.py starts when the panel is touched and stops when it goes idle.
exec runuser -u kiosk -- matchbox-window-manager -use_titlebar no -use_cursor no
