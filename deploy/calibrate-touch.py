#!/usr/bin/env python3
"""Calibrate the 3.5" panel's touch against crosshairs drawn on the panel.

Run as root on the Pi: it stops the panel's interface, draws five crosshairs one at a time, and you tap
the centre of each with a fingertip (or better, a stylus or fingernail). It fits a libinput
calibration matrix to the taps and prints how far off each tap would land. With --write it
saves the matrix in deploy/99-homeobd-panel.rules and applies it. The panel restarts at the
end either way. See docs/PANEL.md.
"""
import fcntl
import glob
import mmap
import os
import re
import struct
import subprocess
import sys

RULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '99-homeobd-panel.rules')
TARGETS = [(0.1, 0.1), (0.9, 0.1), (0.5, 0.5), (0.1, 0.9), (0.9, 0.9)]  # fractions of the screen
EV_KEY, EV_ABS, BTN_TOUCH, ABS_X, ABS_Y = 0x01, 0x03, 0x14A, 0x00, 0x01
EVENT = struct.Struct('llHHi')  # struct input_event
WHITE, BLACK = b'\xff\xff', b'\x00\x00'  # RGB565


def find_touch():
    for path in sorted(glob.glob('/sys/class/input/event*/device/name')):
        if open(path).read().strip() == 'ADS7846 Touchscreen':
            return '/dev/input/' + path.split('/')[4]
    sys.exit('No ADS7846 touchscreen found: is the panel overlay loaded?')


class Screen:
    def __init__(self):
        dev = os.path.realpath('/dev/fb-panel')
        sysfs = '/sys/class/graphics/' + os.path.basename(dev)
        self.w, self.h = map(int, open(sysfs + '/virtual_size').read().split(','))
        self.fd = os.open(dev, os.O_RDWR)
        self.fb = mmap.mmap(self.fd, self.w * self.h * 2)

    def fill(self, colour, x0=0, y0=0, x1=None, y1=None):
        x1, y1 = min(x1 or self.w, self.w), min(y1 or self.h, self.h)
        x0, y0 = max(x0, 0), max(y0, 0)
        row = colour * (x1 - x0)
        for y in range(y0, y1):
            off = (y * self.w + x0) * 2
            self.fb[off:off + len(row)] = row

    def crosshair(self, x, y, colour):
        self.fill(colour, x - 20, y - 1, x + 21, y + 2)
        self.fill(colour, x - 1, y - 20, x + 2, y + 21)


def abs_range(fd, axis):
    buf = bytearray(24)  # struct input_absinfo
    fcntl.ioctl(fd, 0x80184540 + axis, buf)  # EVIOCGABS(axis)
    _, lo, hi = struct.unpack_from('iii', buf)
    return lo, hi


def read_tap(f, rx, ry):
    """One press, normalised to 0..1 of each axis' range: the median of the samples, leaving
    out the first and last fifth (a resistive panel reads unreliably as the finger lands and
    lifts)."""
    x = y = None
    xs, ys, down = [], [], False
    while True:
        _, _, etype, code, value = EVENT.unpack(f.read(EVENT.size))
        if etype == EV_ABS and code == ABS_X:
            x = value
        elif etype == EV_ABS and code == ABS_Y:
            y = value
        elif etype == EV_KEY and code == BTN_TOUCH:
            down = bool(value)
            if not down and len(xs) >= 3:
                cut = len(xs) // 5
                mx = sorted(xs[cut:len(xs) - cut])[(len(xs) - 2 * cut) // 2]
                my = sorted(ys[cut:len(ys) - cut])[(len(ys) - 2 * cut) // 2]
                return (mx - rx[0]) / (rx[1] - rx[0]), (my - ry[0]) / (ry[1] - ry[0])
            xs, ys = [], []
        if down and etype == 0 and x is not None and y is not None:  # EV_SYN
            xs.append(x)
            ys.append(y)


def solve3(m, v):
    """Solve the 3x3 system m @ out = v (Cramer's rule)."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-9:
        sys.exit('The taps were in a line; run it again.')
    return [det([[v[r] if c == i else m[r][c] for c in range(3)] for r in range(3)]) / d
            for i in range(3)]


def fit(taps, goals):
    """Least-squares affine fit: the row (a, b, c) with a*tx + b*ty + c closest to goals."""
    rows = [(tx, ty, 1.0) for tx, ty in taps]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    atb = [sum(r[i] * g for r, g in zip(rows, goals)) for i in range(3)]
    return solve3(ata, atb)


def main():
    # The power daemon would start the browser on the first tap, and X would draw over us.
    subprocess.run(['systemctl', 'stop', 'homeobd-panel-power', 'homeobd-kiosk'], check=False)
    try:
        screen = Screen()
        screen.fill(WHITE)
        taps = []
        with open(find_touch(), 'rb', buffering=0) as f:
            rx, ry = abs_range(f.fileno(), ABS_X), abs_range(f.fileno(), ABS_Y)
            for n, (fx, fy) in enumerate(TARGETS, 1):
                x, y = round(fx * (screen.w - 1)), round(fy * (screen.h - 1))
                screen.crosshair(x, y, BLACK)
                print(f'Tap the centre of crosshair {n} of {len(TARGETS)}...', flush=True)
                taps.append(read_tap(f, rx, ry))
                screen.crosshair(x, y, WHITE)
        row1 = fit(taps, [fx for fx, _ in TARGETS])
        row2 = fit(taps, [fy for _, fy in TARGETS])
        print('\nWhere each tap lands with this matrix (pixels off target):')
        for (tx, ty), (fx, fy) in zip(taps, TARGETS):
            dx = (row1[0] * tx + row1[1] * ty + row1[2] - fx) * screen.w
            dy = (row2[0] * tx + row2[1] * ty + row2[2] - fy) * screen.h
            print(f'  target {fx:.1f},{fy:.1f}: {dx:+5.1f} x {dy:+5.1f} y')
        matrix = ' '.join('%.4f' % v for v in row1 + row2)
        print(f'\nENV{{LIBINPUT_CALIBRATION_MATRIX}}="{matrix}"')
        if '--write' in sys.argv:
            rule = open(RULE).read()
            rule = re.sub(r'LIBINPUT_CALIBRATION_MATRIX}="[^"]*"',
                          f'LIBINPUT_CALIBRATION_MATRIX}}="{matrix}"', rule)
            open(RULE, 'w').write(rule)
            subprocess.run(['install', '-m', '644', RULE, '/etc/udev/rules.d/'], check=True)
            subprocess.run(['udevadm', 'trigger', '--subsystem-match=input'], check=True)
            subprocess.run(['udevadm', 'settle'], check=True)
            print(f'Saved in {RULE} and applied.')
    finally:
        subprocess.run(['systemctl', 'start', 'homeobd-kiosk', 'homeobd-panel-power'], check=False)


if __name__ == '__main__':
    main()
