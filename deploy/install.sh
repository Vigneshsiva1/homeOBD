#!/bin/sh
# Install or update the homeOBD systemd units and start them. Safe to re-run after
# pulling changes: it refreshes the venv, copies the units and restarts the app.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p data backups
chmod +x deploy/backup.sh

install -m 644 deploy/homeobd.service deploy/homeobd-backup.service deploy/homeobd-backup.timer \
    /etc/systemd/system/
systemctl daemon-reload
systemctl enable homeobd.service homeobd-backup.timer
systemctl restart homeobd.service
systemctl start homeobd-backup.timer

systemctl --no-pager --lines=0 status homeobd.service
