"""Web Push: this unit's VAPID keys, phone subscriptions, sending, and the notification schedule.

The Pi sends each notification to the phone's push service (Apple's, for an iPhone), which
delivers it; nothing on the Pi is reachable from the internet. The schedule rules live in
engine.slot_codes; run_schedule decides when a slot is due and sends it once.
"""

import base64
import json
import logging
import os
import sqlite3
from collections.abc import Callable
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from . import engine, service

log = logging.getLogger("homeobd.push")

# The VAPID "sub" claim: who to contact about this sender. A URL avoids sharing an email address.
SUBJECT = os.environ.get("HOMEOBD_PUSH_SUBJECT", "https://photostorage.tail82999e.ts.net")
TTL_SECONDS = 12 * 3600  # keep trying for 12 h if the phone is offline (0 would drop it)

Sender = Callable[[dict, str], None]


def public_key(conn: sqlite3.Connection) -> str:
    """The unit's VAPID public key (base64url), creating the key pair on first use."""
    row = conn.execute("SELECT public_key FROM push_keys WHERE id = 1").fetchone()
    if row:
        return row["public_key"]
    vapid = Vapid()
    vapid.generate_keys()
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    conn.execute(
        "INSERT INTO push_keys (id, private_pem, public_key) VALUES (1, ?, ?)",
        (vapid.private_pem().decode(), key),
    )
    conn.commit()
    return key


def _vapid(conn: sqlite3.Connection) -> Vapid:
    public_key(conn)  # make sure the keys exist
    pem = conn.execute("SELECT private_pem FROM push_keys WHERE id = 1").fetchone()[0]
    return Vapid.from_pem(pem.encode())


def subscribe(conn: sqlite3.Connection, endpoint: str, p256dh: str, auth: str, user_agent: str, at: datetime) -> None:
    conn.execute(
        "INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_agent, created_at)"
        " VALUES (?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET"
        " p256dh = excluded.p256dh, auth = excluded.auth, user_agent = excluded.user_agent",
        (endpoint, p256dh, auth, user_agent, at.isoformat()),
    )
    conn.commit()


def unsubscribe(conn: sqlite3.Connection, endpoint: str) -> bool:
    removed = conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).rowcount
    conn.commit()
    return removed > 0


def subscription_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0]


class Gone(Exception):
    """The push service says this subscription no longer exists."""


def webpush_sender(conn: sqlite3.Connection) -> Sender:
    vapid = _vapid(conn)

    def send(subscription: dict, payload: str) -> None:
        try:
            webpush(
                subscription,
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": SUBJECT},
                ttl=TTL_SECONDS,
                timeout=15,
            )
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                raise Gone() from e
            raise

    return send


def send_all(conn: sqlite3.Connection, title: str, body: str, tag: str, sender: Sender | None = None) -> dict:
    """Send one notification to every subscribed device. Drops subscriptions that are gone."""
    send = sender or webpush_sender(conn)
    payload = json.dumps({"title": title, "body": body, "tag": tag, "url": "/"})
    result = {"sent": 0, "removed": 0, "failed": 0}
    rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
    for r in rows:
        sub = {"endpoint": r["endpoint"], "keys": {"p256dh": r["p256dh"], "auth": r["auth"]}}
        try:
            send(sub, payload)
            result["sent"] += 1
        except Gone:
            unsubscribe(conn, r["endpoint"])
            result["removed"] += 1
        except Exception:
            log.exception("push to %s failed", r["endpoint"][:40])
            result["failed"] += 1
    return result


def run_schedule(conn: sqlite3.Connection, at: datetime, sender: Sender | None = None) -> list[str]:
    """Send any notification slot that is due now and not yet handled today. Returns the slots
    handled. A slot counts as handled even when nothing was due, so it never fires twice."""
    handled = []
    today = at.date().isoformat()
    for slot, when in engine.SLOTS.items():
        start = datetime.combine(at.date(), when, tzinfo=at.tzinfo)
        if not (start <= at < start + engine.SLOT_GRACE):
            continue
        if conn.execute("SELECT 1 FROM notify_log WHERE date = ? AND slot = ?", (today, slot)).fetchone():
            continue
        codes = engine.slot_codes(slot, at.weekday(), service.load_codes(conn, at))
        if codes and subscription_count(conn):
            title, body = engine.notification_text(codes)
            send_all(conn, title, body, tag=f"{today}-{slot}", sender=sender)
        conn.execute(
            "INSERT INTO notify_log (date, slot, sent_at, codes) VALUES (?, ?, ?, ?)",
            (today, slot, at.isoformat(), ",".join(c.code for c in codes)),
        )
        conn.commit()
        handled.append(slot)
    return handled
