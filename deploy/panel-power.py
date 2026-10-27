#!/usr/bin/env python3
"""Keep the 3.5" panel's interface off until it is wanted.

The browser (homeobd-panel-ui.service) only runs while the panel is on: a tap turns it on
until nobody has touched it for IDLE_OFF seconds, and a newly set code (or one that gets
worse, PEND -> CONF -> PERM) turns it on for CODE_WAKE seconds. Codes set during the quiet
hours wait until they end, so the daily codes set at midnight light the panel in the morning.
The scan tool's SCREEN OFF button turns it off at once (a POST to OFF_ADDR, which only
listens locally). Off, the panel is drawn black: its backlight is wired always-on and can't be switched.

Runs as root from homeobd-panel-power.service. See docs/PANEL.md.
"""
import glob
import http.server
import json
import mmap
import os
import select
import struct
import subprocess
import time
import urllib.request
from datetime import datetime

IDLE_OFF = 60  # seconds after the last touch
CODE_WAKE = 30  # seconds on for a new or worse code
QUIET = (22, 8)  # hours: code wakes from 22:00 wait until 08:00
POLL = 60  # seconds between code checks
UI = 'homeobd-panel-ui.service'
CODES_URL = 'http://127.0.0.1:8000/api/codes'
OFF_ADDR = ('127.0.0.1', 8001)  # POST /off here turns the panel off (scantool.js panelOff)
STATE_RANK = {'PERM': 0, 'CONF': 1, 'PEND': 2}  # as in app/engine.py: lower is worse
EV_KEY, BTN_TOUCH = 0x01, 0x14A
EVENT = struct.Struct('llHHi')  # struct input_event

# 5 x 7 pixel letters for the splash shown while the browser starts (about 5 s).
FONT = {
    'A': '01110 10001 10001 11111 10001 10001 10001', 'B': '11110 10001 10001 11110 10001 10001 11110',
    'D': '11110 10001 10001 10001 10001 10001 11110', 'G': '01110 10001 10000 10111 10001 10001 01111',
    'I': '01110 00100 00100 00100 00100 00100 01110', 'K': '10001 10010 10100 11000 10100 10010 10001',
    'L': '10000 10000 10000 10000 10000 10000 11111', 'N': '10001 11001 10101 10011 10001 10001 10001',
    'O': '01110 10001 10001 10001 10001 10001 01110', 'P': '11110 10001 10001 11110 10000 10000 10000',
    'T': '11111 00100 00100 00100 00100 00100 00100', '-': '00000 00000 00000 11111 00000 00000 00000',
    '.': '00000 00000 00000 00000 00000 00000 00100', ' ': '00000 00000 00000 00000 00000 00000 00000',
}
BLACK, GREY = b'\x00\x00', struct.pack('<H', (23 << 11) | (47 << 5) | 23)  # RGB565, grey ~75 %


class Panel:
    """The panel's framebuffer. Writes through the mmap reach the panel within ~0.3 s (fbtft
    sends the changed lines), while X sits idle with no window to draw."""

    def __init__(self):
        dev = os.path.realpath('/dev/fb-panel')
        sysfs = '/sys/class/graphics/' + os.path.basename(dev)
        self.w, self.h = map(int, open(sysfs + '/virtual_size').read().split(','))
        self.fd = os.open(dev, os.O_RDWR)
        self.fb = mmap.mmap(self.fd, self.w * self.h * 2)

    def black(self):
        self.fb[:] = BLACK * (self.w * self.h)

    def text(self, y, s, scale=4):
        x0 = (self.w - len(s) * 6 * scale) // 2
        for n, ch in enumerate(s):
            for r, bits in enumerate(FONT[ch].split()):
                for c, bit in enumerate(bits):
                    if bit == '1':
                        x, yy = x0 + (n * 6 + c) * scale, y + r * scale
                        for dy in range(scale):
                            off = ((yy + dy) * self.w + x) * 2
                            self.fb[off:off + 2 * scale] = GREY * scale

    def splash(self):
        self.black()
        self.text(self.h // 2 - 60, 'APT-OBD')
        self.text(self.h // 2 + 20, 'LINKING...', scale=3)


class OffRequest(http.server.BaseHTTPRequestHandler):
    timeout = 2  # seconds; a stalled client can't hold up the touch loop

    def do_POST(self):
        self.server.off = self.path == '/off'
        self.send_response(204)
        # The scan tool is on another port (another origin); without this its fetch fails,
        # although the request has already arrived.
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def log_message(self, *args):
        pass


def touch_device():
    for path in sorted(glob.glob('/sys/class/input/event*/device/name')):
        if open(path).read().strip() == 'ADS7846 Touchscreen':
            return open('/dev/input/' + path.split('/')[4], 'rb', buffering=0)
    raise SystemExit('No ADS7846 touchscreen found: is the panel overlay loaded?')


def read_codes():
    """{code: rank} of the active codes, or None when the app can't be reached."""
    try:
        with urllib.request.urlopen(CODES_URL, timeout=5) as r:
            return {c['code']: STATE_RANK.get(c['state'], 3) for c in json.load(r)['codes']}
    except (OSError, ValueError, KeyError):
        return None


def quiet(now):
    start, end = QUIET
    return now.hour >= start or now.hour < end


def systemctl(*args):
    subprocess.run(['systemctl', *args], check=False)


def main():
    panel, touch = Panel(), touch_device()
    server = http.server.HTTPServer(OFF_ADDR, OffRequest)
    server.off = False
    on_until = 0.0
    seen = read_codes() or {}
    pending = False  # a code wake held back by the quiet hours
    next_poll = time.monotonic() + POLL

    def turn_on(seconds):
        nonlocal on_until
        if not on_until:
            panel.splash()
            systemctl('start', '--no-block', UI)
        on_until = max(on_until, time.monotonic() + seconds)

    panel.black()
    systemctl('stop', UI)
    turn_on(CODE_WAKE)  # show it once at boot, so it is clear the panel works
    while True:
        ready, _, _ = select.select([touch, server], [], [], 1)
        now = time.monotonic()
        if server in ready:
            server.handle_request()
            if server.off and on_until:
                on_until = now
            server.off = False
        if touch in ready:
            data = touch.read(EVENT.size * 64)
            for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, i)
                if etype == EV_KEY and code == BTN_TOUCH and value == 1:
                    turn_on(IDLE_OFF)
        if now >= next_poll:
            next_poll = now + POLL
            codes = read_codes()
            if codes is not None:
                if any(rank < seen.get(code, 99) for code, rank in codes.items()):
                    pending = True
                seen = codes
        if pending and not quiet(datetime.now()):
            pending = False
            turn_on(CODE_WAKE)
        if on_until and now >= on_until:
            on_until = 0.0
            systemctl('stop', UI)
            time.sleep(0.5)  # let X repaint where the browser was, then cover it
            panel.black()


if __name__ == '__main__':
    main()
