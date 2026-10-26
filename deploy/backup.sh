#!/bin/sh
# Nightly SQLite backup: a consistent copy of data/homeobd.db (safe while the app is
# running), checked for integrity, keeping the newest $KEEP copies. Run by
# homeobd-backup.timer; can also be run by hand.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB="${HOMEOBD_DB:-$ROOT/data/homeobd.db}"
DEST="${HOMEOBD_BACKUP_DIR:-$ROOT/backups}"
KEEP="${HOMEOBD_BACKUP_KEEP:-14}"

mkdir -p "$DEST"
out="$DEST/homeobd-$(date +%Y-%m-%d).db"

sqlite3 "$DB" ".backup '$out.tmp'"
if [ "$(sqlite3 "$out.tmp" 'PRAGMA integrity_check;')" != "ok" ]; then
    rm -f "$out.tmp"
    echo "backup failed integrity check" >&2
    exit 1
fi
mv "$out.tmp" "$out"

# Keep the newest $KEEP backups; names sort by date.
ls -1 "$DEST"/homeobd-????-??-??.db | sort -r | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
done

echo "backed up to $out"
