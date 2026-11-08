"""Dependency-free illustrator for demo product photos (flat garment silhouettes as PNG).

    from demo_images import render_photos
    pngs = render_photos("hoodie", "#2e4a7d")      # list of PNG bytes: front, flat-lay, detail

These are placeholders so the shop looks alive. Replace them with real photos from Products > Manage photos.
"""
import math
import struct
import zlib

W, H, SS = 400, 500, 2          # output size, supersampling factor (smooths the edges)


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def _shade(c, f):
    return tuple(max(0, min(255, round(v * f))) for v in c)


SHADES = {"m": 1.0, "s": 0.92, "d": 0.8, "k": 0.55, "l": 1.1}


class Canvas:
    def __init__(self, w, h, top, bottom):
        self.w, self.h = w, h
        self.rows = [bytearray(bytes(_mix(top, bottom, y / (h - 1))) * w) for y in range(h)]

    def polygon(self, pts, color):
        """Even-odd scanline fill."""
        n = len(pts)
        ys = [p[1] for p in pts]
        y0, y1 = max(0, int(math.floor(min(ys)))), min(self.h - 1, int(math.ceil(max(ys))))
        col = bytes(color)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
                if (ya <= yc < yb) or (yb <= yc < ya):
                    xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            row = self.rows[y]
            for k in range(0, len(xs) - 1, 2):
                xa, xb = max(0, int(round(xs[k]))), min(self.w, int(round(xs[k + 1])))
                if xb > xa:
                    row[3 * xa:3 * xb] = col * (xb - xa)


def _downsample(rows, w2, h2):
    out = []
    for y in range(h2):
        a, b = rows[2 * y], rows[2 * y + 1]
        row = bytearray(3 * w2)
        for c in range(3):
            e0, o0, e1, o1 = a[c::6], a[c + 3::6], b[c::6], b[c + 3::6]
            row[c::3] = bytes((p + q + r + s + 2) >> 2 for p, q, r, s in zip(e0, o0, e1, o1))
        out.append(row)
    return out


def _png(rows, w, h):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- shapes (0..1 coordinates)
def arc(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def bar(x0, y0, x1, y1, t):
    """A thin line from (x0,y0) to (x1,y1) as a quad of thickness t."""
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln * t / 2, dx / ln * t / 2
    return [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def tee():
    body = [(0.38, 0.17), (0.18, 0.23), (0.04, 0.39), (0.14, 0.47), (0.24, 0.4), (0.24, 0.88),
            (0.76, 0.88), (0.76, 0.4), (0.86, 0.47), (0.96, 0.39), (0.82, 0.23), (0.62, 0.17)]
    return [(body, "m"), ([(0.5, 0.22), (0.62, 0.17), (0.82, 0.23), (0.96, 0.39), (0.86, 0.47), (0.76, 0.4), (0.76, 0.88), (0.5, 0.88)], "s"),
            (arc(0.5, 0.17, 0.13, 0.085, 0, 180), "d"), (arc(0.5, 0.17, 0.105, 0.06, 0, 180), "k"),
            (rect(0.24, 0.84, 0.76, 0.88), "d")]


def tank():
    body = [(0.36, 0.14), (0.29, 0.14), (0.26, 0.4), (0.22, 0.88), (0.78, 0.88), (0.74, 0.4), (0.71, 0.14),
            (0.64, 0.14), (0.5, 0.31)]
    return [(body, "m"), ([(0.5, 0.31), (0.64, 0.14), (0.71, 0.14), (0.74, 0.4), (0.78, 0.88), (0.5, 0.88)], "s"), (arc(0.5, 0.14, 0.14, 0.17, 0, 180), "k"),
            (rect(0.22, 0.84, 0.78, 0.88), "d")]


def hoodie():
    hood = arc(0.5, 0.2, 0.19, 0.14, 180, 360) + [(0.66, 0.24), (0.34, 0.24)]
    body = [(0.35, 0.18), (0.17, 0.25), (0.06, 0.68), (0.17, 0.73), (0.25, 0.42), (0.25, 0.9),
            (0.75, 0.9), (0.75, 0.42), (0.83, 0.73), (0.94, 0.68), (0.83, 0.25), (0.65, 0.18), (0.5, 0.28)]
    return [(hood, "d"), (body, "m"), ([(0.5, 0.28), (0.65, 0.18), (0.83, 0.25), (0.94, 0.68), (0.83, 0.73), (0.75, 0.42), (0.75, 0.9), (0.5, 0.9)], "s"),
            (arc(0.5, 0.2, 0.12, 0.08, 0, 180), "k"),
            ([(0.31, 0.64), (0.69, 0.64), (0.75, 0.84), (0.25, 0.84)], "d"),
            (rect(0.25, 0.86, 0.75, 0.9), "d"), (rect(0.06, 0.66, 0.17, 0.73), "d"), (rect(0.83, 0.66, 0.94, 0.73), "d"),
            (bar(0.44, 0.27, 0.43, 0.43, 0.012), "l"), (bar(0.56, 0.27, 0.57, 0.43, 0.012), "l")]


def jacket():
    body = [(0.36, 0.17), (0.17, 0.24), (0.06, 0.7), (0.17, 0.75), (0.25, 0.42), (0.25, 0.86),
            (0.75, 0.86), (0.75, 0.42), (0.83, 0.75), (0.94, 0.7), (0.83, 0.24), (0.64, 0.17)]
    out = [(body, "m"), ([(0.5, 0.3), (0.64, 0.17), (0.83, 0.24), (0.94, 0.7), (0.83, 0.75), (0.75, 0.42), (0.75, 0.86), (0.5, 0.86)], "s"),
           ([(0.36, 0.17), (0.5, 0.3), (0.5, 0.2)], "d"), ([(0.64, 0.17), (0.5, 0.3), (0.5, 0.2)], "d"),
           (bar(0.5, 0.3, 0.5, 0.86, 0.012), "k"), (rect(0.29, 0.4, 0.42, 0.5), "s"), (rect(0.58, 0.4, 0.71, 0.5), "s"),
           (rect(0.25, 0.82, 0.75, 0.86), "d")]
    for i in range(5):
        y = 0.36 + i * 0.1
        out.append((arc(0.46, y, 0.012, 0.009, 0, 360, 10), "l"))
    return out


def pants():
    body = [(0.28, 0.1), (0.72, 0.1), (0.79, 0.92), (0.55, 0.92), (0.5, 0.4), (0.45, 0.92), (0.21, 0.92)]
    return [(body, "m"), ([(0.5, 0.4), (0.55, 0.92), (0.79, 0.92), (0.72, 0.1), (0.5, 0.1)], "s"),
            (rect(0.28, 0.1, 0.72, 0.16), "d"), (bar(0.5, 0.16, 0.5, 0.4, 0.01), "k"),
            (bar(0.3, 0.17, 0.36, 0.3, 0.01), "k"), (bar(0.7, 0.17, 0.64, 0.3, 0.01), "k"),
            (rect(0.21, 0.88, 0.45, 0.92), "d"), (rect(0.55, 0.88, 0.79, 0.92), "d")]


def shorts():
    body = [(0.26, 0.2), (0.74, 0.2), (0.81, 0.66), (0.55, 0.66), (0.5, 0.44), (0.45, 0.66), (0.19, 0.66)]
    return [(body, "m"), ([(0.5, 0.44), (0.55, 0.66), (0.81, 0.66), (0.74, 0.2), (0.5, 0.2)], "s"),
            (rect(0.26, 0.2, 0.74, 0.26), "d"), (bar(0.5, 0.26, 0.5, 0.44, 0.01), "k"),
            (rect(0.2, 0.46, 0.35, 0.58), "d"), (rect(0.65, 0.46, 0.8, 0.58), "d")]


def cap():
    crown = arc(0.5, 0.56, 0.27, 0.27, 180, 360, 32)
    return [(arc(0.5, 0.57, 0.36, 0.1, 0, 180, 32), "d"), (crown + [(0.77, 0.56), (0.23, 0.56)], "m"),
            ([(0.5, 0.29), (0.62, 0.34), (0.6, 0.56), (0.5, 0.56)], "s"),
            (bar(0.5, 0.3, 0.5, 0.56, 0.008), "k"), (arc(0.5, 0.3, 0.025, 0.02, 0, 360, 12), "d")]


def hat():
    return [(arc(0.5, 0.6, 0.44, 0.1, 0, 360, 36), "d"),
            ([(0.3, 0.3), (0.7, 0.3), (0.76, 0.58), (0.24, 0.58)], "m"),
            (arc(0.5, 0.3, 0.2, 0.05, 0, 360, 24), "l"),
            ([(0.5, 0.3), (0.7, 0.3), (0.76, 0.58), (0.5, 0.58)], "s"),
            (rect(0.245, 0.5, 0.755, 0.56), "k")]


def tote():
    def handle(cx):
        return arc(cx, 0.4, 0.09, 0.26, 180, 360, 20) + arc(cx, 0.4, 0.07, 0.24, 360, 180, 20)
    return [(handle(0.38), "d"), (handle(0.62), "d"),
            ([(0.2, 0.4), (0.8, 0.4), (0.82, 0.9), (0.18, 0.9)], "m"),
            ([(0.5, 0.4), (0.8, 0.4), (0.82, 0.9), (0.5, 0.9)], "s"),
            (rect(0.3, 0.55, 0.7, 0.75), "d")]


SHAPES = {"tee": tee, "tank": tank, "hoodie": hoodie, "jacket": jacket, "pants": pants,
          "shorts": shorts, "cap": cap, "hat": hat, "tote": tote}


# ---------------------------------------------------------------- rendering
def _transform(view):
    """Returns f(x, y) -> (x, y) in 0..1 space for each photo angle."""
    if view == "tilt":
        a, s = math.radians(-9), 0.86
        return lambda x, y: (0.5 + s * ((x - .5) * math.cos(a) - (y - .5) * math.sin(a)),
                             0.52 + s * ((x - .5) * math.sin(a) + (y - .5) * math.cos(a)))
    if view == "detail":
        return lambda x, y: (0.5 + 1.75 * (x - 0.5), 0.36 + 1.75 * (y - 0.2))
    return lambda x, y: (0.5 + 0.92 * (x - 0.5), 0.5 + 0.92 * (y - 0.5) - 0.01)


def render(kind, hex_color, view="front"):
    color = _hex(hex_color)
    light = _lum(color) > 0.78
    if view == "tilt":
        base = _mix(color, (255, 255, 255), 0.82)
        top, bottom = (_mix(base, (255, 255, 255), .5), base)
    elif view == "detail":
        top, bottom = ((205, 209, 216), (186, 191, 200))
    else:
        top, bottom = ((226, 229, 234), (212, 216, 223)) if light else ((246, 247, 249), (232, 235, 239))
    cv = Canvas(W * SS, H * SS, top, bottom)
    if view == "tilt":                                    # diagonal stripes behind the flat-lay
        stripe = _shade(bottom, 0.96)
        for x in range(-H * SS, W * SS, 70 * SS):
            cv.polygon([(x, 0), (x + 34 * SS, 0), (x + 34 * SS + H * SS, H * SS), (x + H * SS, H * SS)], stripe)
    f = _transform(view)
    if view != "detail":                                  # soft shadow under the garment
        sh = [f(x, y) for x, y in arc(0.5, 0.93, 0.34, 0.03, 0, 360, 30)]
        cv.polygon([(x * W * SS, y * H * SS) for x, y in sh], _shade(bottom, 0.9))
    for pts, tone in SHAPES[kind]():
        cv.polygon([(x * W * SS, y * H * SS) for x, y in (f(px, py) for px, py in pts)],
                   _shade(color, SHADES[tone]))
    return _png(_downsample(cv.rows, W, H), W, H)


def render_photos(kind, hex_color, views=("front", "tilt", "detail")):
    return [render(kind, hex_color, v) for v in views]
