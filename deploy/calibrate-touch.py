#!/usr/bin/env python3
"""Calibrate the 3.5" panel's touch: tap three corners, get a libinput calibration matrix.

Run on the Pi with the kiosk showing, then tap, in order, close to the edges:
top-left, top-right, bottom-left. Prints the matrix for deploy/99-homeobd-panel.rules.
See docs/PANEL.md.
"""
import fcntl
import glob
import struct
import sys

# Where a fingertip lands when aiming at each corner: about 10 px in from both edges.
CORNERS = [('top-left', 0.03, 0.02), ('top-right', 0.97, 0.02), ('bottom-left', 0.03, 0.98)]
EV_KEY, EV_ABS, BTN_TOUCH, ABS_X, ABS_Y = 0x01, 0x03, 0x14A, 0x00, 0x01
EVENT = struct.Struct('llHHi')  # struct input_event


def find_device():
    for path in sorted(glob.glob('/sys/class/input/event*/device/name')):
        if open(path).read().strip() == 'ADS7846 Touchscreen':
            return '/dev/input/' + path.split('/')[4]
    sys.exit('No ADS7846 touchscreen found: is the panel overlay loaded?')


def abs_range(fd, axis):
    buf = bytearray(24)  # struct input_absinfo
    fcntl.ioctl(fd, 0x80184540 + axis, buf)  # EVIOCGABS(axis)
    _, lo, hi = struct.unpack_from('iii', buf)
    return lo, hi


def read_tap(f, rx, ry):
    """Average position of one press, normalised to 0..1 of each axis' range."""
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
            if not down and xs:
                return (sum(xs) / len(xs) - rx[0]) / (rx[1] - rx[0]), \
                       (sum(ys) / len(ys) - ry[0]) / (ry[1] - ry[0])
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
    if abs(d) < 1e-6:
        sys.exit('The three taps were in a line; run it again.')
    return [det([[v[r] if c == i else m[r][c] for c in range(3)] for r in range(3)]) / d
            for i in range(3)]


def main():
    dev = find_device()
    with open(dev, 'rb', buffering=0) as f:
        rx, ry = abs_range(f.fileno(), ABS_X), abs_range(f.fileno(), ABS_Y)
        taps = []
        for name, *_ in CORNERS:
            print(f'Tap the {name} corner...', flush=True)
            taps.append(read_tap(f, rx, ry))
            print('  raw %.3f, %.3f' % taps[-1])
    m = [[tx, ty, 1.0] for tx, ty in taps]
    row1 = solve3(m, [sx for _, sx, _ in CORNERS])
    row2 = solve3(m, [sy for _, _, sy in CORNERS])
    matrix = ' '.join('%.4f' % v for v in row1 + row2)
    print(f'\nENV{{LIBINPUT_CALIBRATION_MATRIX}}="{matrix}"\n'
          'Put it in deploy/99-homeobd-panel.rules, re-run deploy/install-kiosk.sh and\n'
          'systemctl restart homeobd-kiosk.')


if __name__ == '__main__':
    main()
