"""Foto-Layouts und Rahmen: setzt eine oder mehrere Aufnahmen zu einem druckfertigen Bild zusammen.

Alle Layouts ergeben ein 10x15-cm-Bild (Seitenverhältnis 3:2, 300 dpi), damit
sie randlos auf Fotopapier gedruckt werden können. Die Rahmen werden als
Vektorgrafik gezeichnet und sind deshalb in jeder Grösse scharf.

Koordinaten beziehen sich immer auf die Grundgrösse 1800x1200 (bzw. 1200x1800).
Für Vorschaubilder wird mit dem Faktor `k` verkleinert gerendert.
"""
import datetime
import functools
import io
import math
import os
import random

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")
SS = 2  # Supersampling für glatte Kanten

LAYOUTS = {
    "single": {"label": "Einzelbild", "shots": 1},
    "strip": {"label": "Fotostreifen", "shots": 3},
    "grid": {"label": "4er-Collage", "shots": 4},
}

# Ältere Einstellungen weiterverwenden
LEGACY_LAYOUTS = {"classic": "single", "polaroid": "single"}
LEGACY_FRAMES = {"bunt": "geburtstag", "elegant": "hochzeit", "nacht": "silvester"}


# --------------------------------------------------------------------------- Grundlagen
def C(color, alpha=255):
    return ImageColor.getrgb(color)[:3] + (alpha,)


def mix(c1, c2, t):
    a, b = ImageColor.getrgb(c1), ImageColor.getrgb(c2)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


@functools.lru_cache(maxsize=64)
def _font(name, size, weight=None):
    try:
        font = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        if weight:
            font.set_variation_by_name(weight)
        return font
    except (OSError, ValueError):
        return ImageFont.load_default(size=size)


def _gradient(size, top, bottom):
    mask = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)


class Painter:
    """Zeichenfläche mit Supersampling; Koordinaten in Grundgrösse."""

    def __init__(self, size, k):
        self.size = size
        self.f = k * SS
        self.img = Image.new("RGBA", (size[0] * SS, size[1] * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _xy(self, pts):
        return [(x * self.f, y * self.f) for x, y in pts]

    def _w(self, w):
        return max(1, round(w * self.f))

    def ellipse(self, box, fill=None, outline=None, width=1):
        x1, y1, x2, y2 = box
        self.d.ellipse([min(x1, x2) * self.f, min(y1, y2) * self.f, max(x1, x2) * self.f, max(y1, y2) * self.f],
                       fill=fill, outline=outline, width=self._w(width))

    def circle(self, cx, cy, r, **kw):
        self.ellipse((cx - r, cy - r, cx + r, cy + r), **kw)

    def polygon(self, pts, fill):
        self.d.polygon(self._xy(pts), fill=fill)

    def line(self, pts, fill, width=2):
        self.d.line(self._xy(pts), fill=fill, width=self._w(width), joint="curve")

    def rect(self, box, fill=None, outline=None, width=1, radius=0):
        self.d.rounded_rectangle([v * self.f for v in box], radius=radius * self.f, fill=fill,
                                 outline=outline, width=self._w(width) if outline else 0)

    def text(self, xy, text, size, fill, font="Baloo2.ttf", weight="ExtraBold"):
        self.d.text((xy[0] * self.f, xy[1] * self.f), text, fill=fill, anchor="mm",
                    font=_font(font, max(6, round(size * self.f)), weight))

    def layer(self):
        return self.img.resize(self.size, Image.LANCZOS)


# --------------------------------------------------------------------------- Motive
def confetti(p, g, rnd, colors, density=9000):
    for _ in range(int(g["W"] * g["H"] / density)):
        x, y, r = rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(4, 13)
        color = C(rnd.choice(colors), rnd.randint(150, 240))
        if rnd.random() < 0.45:
            p.circle(x, y, r, fill=color)
        else:
            a = rnd.uniform(0, math.pi)
            dx, dy = math.cos(a), math.sin(a)
            w, h = r * 1.3, r * 0.5
            p.polygon([(x + dx * w - dy * h, y + dy * w + dx * h), (x + dx * w + dy * h, y + dy * w - dx * h),
                       (x - dx * w + dy * h, y - dy * w - dx * h), (x - dx * w - dy * h, y - dy * w + dx * h)],
                      fill=color)


def star(p, cx, cy, r, fill, points=5, inner=0.45, rot=-math.pi / 2):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = rot + i * math.pi / points
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    p.polygon(pts, fill)


def sparkle(p, cx, cy, r, fill):
    star(p, cx, cy, r, fill, points=4, inner=0.22)


def heart(p, cx, cy, s, fill):
    pts = []
    for i in range(72):
        t = i / 72 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s / 34, cy - y * s / 34))
    p.polygon(pts, fill)


def balloon(p, x, y, r, color):
    string = [(x + math.sin(i / 3) * r * 0.12, y + 1.25 * r + i * r * 0.14) for i in range(24)]
    p.line(string, C("#ffffff", 220), 2.5)
    p.ellipse((x - r, y - 1.2 * r, x + r, y + 1.2 * r), fill=C(color))
    p.polygon([(x - 0.14 * r, y + 1.34 * r), (x + 0.14 * r, y + 1.34 * r), (x, y + 1.14 * r)], C(color))
    p.ellipse((x - 0.62 * r, y - 0.85 * r, x - 0.28 * r, y - 0.25 * r), fill=mix(color, "#ffffff", 0.55))


def bunting(p, x0, x1, y, sag, flag_h, colors):
    n = max(6, int((x1 - x0) / (flag_h * 1.25)))
    rope = [(x0 + (x1 - x0) * t / 40, y + sag * math.sin(math.pi * t / 40)) for t in range(41)]
    p.line(rope, C("#ffffff"), 3)
    fw = (x1 - x0) / n
    for i in range(n):
        t0, t1 = i / n, (i + 0.85) / n
        ax, ay = x0 + (x1 - x0) * t0, y + sag * math.sin(math.pi * t0)
        bx, by = x0 + (x1 - x0) * t1, y + sag * math.sin(math.pi * t1)
        p.polygon([(ax, ay), (bx, by), ((ax + bx) / 2, (ay + by) / 2 + flag_h)], C(colors[i % len(colors)]))
    return fw


def streamer(p, x, y, length, angle, color, width=9):
    pts = []
    for i in range(40):
        t = i / 39
        d = t * length
        off = math.sin(t * 5 * math.pi) * 18
        pts.append((x + math.cos(angle) * d - math.sin(angle) * off, y + math.sin(angle) * d + math.cos(angle) * off))
    p.line(pts, C(color), width)


def snowflake(p, cx, cy, r, color, width=3):
    for k in range(6):
        a = k * math.pi / 3
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        p.line([(cx, cy), (ex, ey)], color, width)
        bx, by = cx + 0.6 * r * math.cos(a), cy + 0.6 * r * math.sin(a)
        for s in (-1, 1):
            b = a + s * math.pi / 4
            p.line([(bx, by), (bx + 0.3 * r * math.cos(b), by + 0.3 * r * math.sin(b))], color, width)


def firework(p, cx, cy, r, color, rnd):
    rays = rnd.randint(16, 24)
    for k in range(rays):
        a = k * 2 * math.pi / rays + rnd.uniform(-0.05, 0.05)
        rr = r * rnd.uniform(0.8, 1.0)
        p.line([(cx + 0.3 * rr * math.cos(a), cy + 0.3 * rr * math.sin(a)),
                (cx + rr * math.cos(a), cy + rr * math.sin(a))], C(color, 230), 3)
        p.circle(cx + (rr + 8) * math.cos(a), cy + (rr + 8) * math.sin(a), 4, fill=C(color))
    p.circle(cx, cy, 5, fill=C("#ffffff"))


def sun(p, cx, cy, r):
    for k in range(14):
        a = k * 2 * math.pi / 14
        b1, b2 = a - 0.12, a + 0.12
        p.polygon([(cx + r * 1.08 * math.cos(b1), cy + r * 1.08 * math.sin(b1)),
                   (cx + r * 1.65 * math.cos(a), cy + r * 1.65 * math.sin(a)),
                   (cx + r * 1.08 * math.cos(b2), cy + r * 1.08 * math.sin(b2))], C("#ffb703"))
    p.circle(cx, cy, r, fill=C("#ffd60a"))
    p.circle(cx - r * 0.25, cy - r * 0.25, r * 0.45, fill=C("#ffe566"))


def waves(p, W, H, y0, amp, wavelength, color, phase=0.0):
    pts = [(x, y0 + amp * math.sin(2 * math.pi * x / wavelength + phase)) for x in range(-20, int(W) + 40, 20)]
    p.polygon(pts + [(W + 40, H + 10), (-20, H + 10)], color)


def leaf(p, x, y, angle, length, width, color, droop=0.25):
    left, right = [], []
    ca, sa = math.cos(angle), math.sin(angle)
    for i in range(21):
        t = i / 20
        px, py = x + ca * length * t, y + sa * length * t + droop * length * t * t
        dx, dy = ca, sa + 2 * droop * t
        n = math.hypot(dx, dy)
        nx, ny = -dy / n, dx / n
        w = width * math.sin(math.pi * t) ** 0.8
        left.append((px + nx * w, py + ny * w))
        right.append((px - nx * w, py - ny * w))
    p.polygon(left + right[::-1], color)


def palm(p, x, base_y, h, lean):
    top_x, top_y = x + lean, base_y - h
    segs = 12
    for i in range(segs):
        t0, t1 = i / segs, (i + 1) / segs
        def at(t):
            return x + lean * t * t, base_y - h * t
        (ax, ay), (bx, by) = at(t0), at(t1)
        w0, w1 = h * (0.055 - 0.02 * t0), h * (0.055 - 0.02 * t1)
        p.polygon([(ax - w0, ay), (ax + w0, ay), (bx + w1, by), (bx - w1, by)],
                  C("#9c6b3c") if i % 2 else C("#8a5a2e"))
    for k, deg in enumerate((-178, -150, -122, -95, -62, -32, -5)):
        leaf(p, top_x, top_y, math.radians(deg), h * 0.5, h * 0.06,
             C("#2d9d5a") if k % 2 else C("#1f7a44"), droop=0.45)
    for dx in (-10, 8, -2):
        p.circle(top_x + dx, top_y + 14 + abs(dx), h * 0.028, fill=C("#6b4423"))


def cloud(p, cx, cy, s, color):
    p.ellipse((cx - 0.9 * s, cy - 0.15 * s, cx + 0.9 * s, cy + 0.38 * s), fill=color)
    p.circle(cx - 0.4 * s, cy, 0.35 * s, fill=color)
    p.circle(cx + 0.1 * s, cy - 0.15 * s, 0.48 * s, fill=color)
    p.circle(cx + 0.55 * s, cy + 0.05 * s, 0.3 * s, fill=color)


def moon(p, cx, cy, r, color):
    p.circle(cx, cy, r, fill=color)
    p.circle(cx + r * 0.45, cy - r * 0.3, r * 0.85, fill=(0, 0, 0, 0))  # Sichel ausschneiden


def plane(p, cx, cy, s, angle, color):
    shape = [(1.0, 0), (0.85, -0.07), (0.2, -0.08), (-0.1, -0.55), (-0.25, -0.55), (-0.05, -0.08),
             (-0.7, -0.07), (-0.85, -0.3), (-0.95, -0.3), (-0.88, 0)]
    shape = shape + [(x, -y) for x, y in reversed(shape[1:-1])]
    ca, sa = math.cos(angle), math.sin(angle)
    p.polygon([(cx + (x * ca - y * sa) * s, cy + (x * sa + y * ca) * s) for x, y in shape], color)


def dotted_curve(p, pts, color, r=4, step=26):
    # quadratische Bézierkurve durch drei Punkte, gepunktet
    (x0, y0), (x1, y1), (x2, y2) = pts
    length = math.hypot(x2 - x0, y2 - y0) + math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(length / step))
    for i in range(n):
        t = i / n
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
        p.circle(x, y, r, fill=color)


def airmail_border(p, W, H, t, colors=("#d62828", "#1d3557")):
    i = 0
    for x in range(-2 * t, int(W) + 2 * t, 2 * t):
        c = C(colors[i % 2])
        p.polygon([(x, 0), (x + t, 0), (x, t), (x - t, t)], c)
        p.polygon([(x, H - t), (x + t, H - t), (x, H), (x - t, H)], c)
        i += 1
    i = 0
    for y in range(-2 * t, int(H) + 2 * t, 2 * t):
        c = C(colors[i % 2])
        p.polygon([(0, y), (t, y - t), (t, y), (0, y + t)], c)
        p.polygon([(W - t, y), (W, y - t), (W, y), (W - t, y + t)], c)
        i += 1


def stamp(p, x, y, w, h, label):
    p.rect((x, y, x + w, y + h), fill=C("#ffffff"))
    r = w / 18
    for i in range(int(w / (2.4 * r)) + 1):  # Zähnung
        cx = x + i * 2.4 * r + r
        p.circle(cx, y, r, fill=(0, 0, 0, 0))
        p.circle(cx, y + h, r, fill=(0, 0, 0, 0))
    for i in range(int(h / (2.4 * r)) + 1):
        cy = y + i * 2.4 * r + r
        p.circle(x, cy, r, fill=(0, 0, 0, 0))
        p.circle(x + w, cy, r, fill=(0, 0, 0, 0))
    ix1, iy1, ix2, iy2 = x + w * 0.13, y + h * 0.11, x + w * 0.87, y + h * 0.89
    p.rect((ix1, iy1, ix2, iy2), fill=C("#48cae4"))
    p.rect((ix1, iy1 + (iy2 - iy1) * 0.62, ix2, iy2), fill=C("#f6dcae"))
    sun(p, ix1 + (ix2 - ix1) * 0.68, iy1 + (iy2 - iy1) * 0.3, (ix2 - ix1) * 0.14)
    p.text(((ix1 + ix2) / 2, iy1 + (iy2 - iy1) * 0.82), label, (iy2 - iy1) * 0.16, C("#1d3557"))


def postmark(p, cx, cy, r, color):
    p.circle(cx, cy, r, outline=color, width=4)
    p.circle(cx, cy, r * 0.78, outline=color, width=2)
    for k in range(4):
        y = cy - r * 0.45 + k * r * 0.3
        p.line([(cx - r * 2.6 + i * 8, y + math.sin(i / 2.5) * 7) for i in range(int(r * 2.2 / 8))], color, 3)


def rings(p, cx, cy, r, color):
    p.circle(cx - 0.5 * r, cy, r, outline=color, width=r * 0.16)
    p.circle(cx + 0.5 * r, cy, r, outline=color, width=r * 0.16)
    dx, dy = cx + 0.5 * r, cy - r * 1.08
    p.polygon([(dx - r * 0.28, dy), (dx, dy - r * 0.26), (dx + r * 0.28, dy), (dx, dy + r * 0.36)], C("#e0f7ff"))


def corner_vine(p, cx, cy, radius, a0, a1, stem, leaf_color, blossom):
    pts = [(cx + radius * math.cos(a0 + (a1 - a0) * i / 30), cy + radius * math.sin(a0 + (a1 - a0) * i / 30))
           for i in range(31)]
    p.line(pts, stem, 4)
    for i in range(3, 30, 4):
        a = a0 + (a1 - a0) * i / 30
        x, y = pts[i]
        side = 1 if i % 8 == 3 else -1
        leaf(p, x, y, a + side * math.pi / 2 + (a1 - a0) / 3, radius * 0.22, radius * 0.06, leaf_color, droop=0)
    for i in (8, 20):
        x, y = pts[i]
        for k in range(5):
            b = k * 2 * math.pi / 5
            p.circle(x + 11 * math.cos(b), y + 11 * math.sin(b), 10, fill=blossom)
        p.circle(x, y, 7, fill=C("#fff3c4"))


def xmas_tree(p, cx, base_y, h, rnd):
    p.rect((cx - h * 0.06, base_y - h * 0.12, cx + h * 0.06, base_y), fill=C("#6b4423"))
    for k, (w, y) in enumerate(((0.5, 0.1), (0.4, 0.35), (0.3, 0.58))):
        top = base_y - h * (y + 0.42)
        p.polygon([(cx - h * w, base_y - h * y), (cx + h * w, base_y - h * y), (cx, top)], C("#2d6a4f" if k % 2 else "#1b4332"))
    for _ in range(8):
        t = rnd.uniform(0.15, 0.8)
        p.circle(cx + rnd.uniform(-0.3, 0.3) * h * (1 - t), base_y - h * t, h * 0.03,
                 fill=C(rnd.choice(["#ffd166", "#e63946", "#ffffff"])))
    star(p, cx, base_y - h * 1.0, h * 0.09, C("#ffd166"))


def ginger_heart(p, cx, cy, s, text):
    heart(p, cx, cy, s * 1.08, C("#fff4e0"))
    heart(p, cx, cy, s * 0.98, C("#8b4a2b"))
    for k in range(10):
        a = k * 2 * math.pi / 10
        p.circle(cx + s * 0.34 * math.cos(a), cy - s * 0.02 + s * 0.26 * math.sin(a), s * 0.025,
                 fill=C(["#e63946", "#ffd166", "#06d6a0"][k % 3]))
    p.text((cx, cy - s * 0.05), text, s * 0.18, C("#fff4e0"))


def raute(p, W, H, d, color):
    for j in range(-1, int(H / (d / 2)) + 2):
        if j % 2:
            continue
        for i in range(-1, int(W / d) + 2):
            cx, cy = i * d, j * d / 2
            p.polygon([(cx, cy - d / 2), (cx + d / 2, cy), (cx, cy + d / 2), (cx - d / 2, cy)], color)


def gold_border(p, W, H, color):
    p.rect((22, 22, W - 22, H - 22), outline=color, width=4)
    p.rect((34, 34, W - 34, H - 34), outline=color, width=1.5)


def seagull(p, x, y, s, color):
    p.line([(x - s, y - s * 0.3), (x - s * 0.5, y - s * 0.5), (x, y)], color, 3)
    p.line([(x, y), (x + s * 0.5, y - s * 0.5), (x + s, y - s * 0.3)], color, 3)


# --------------------------------------------------------------------------- Rahmen
def _band_ends(g, inset=110):
    """Mittelpunkte links/rechts im Textband (für Deko neben dem Titel)."""
    x1, y1, x2, y2 = g["band"]
    return (x1 + inset, (y1 + y2) / 2), (x2 - inset, (y1 + y2) / 2)


def _bottom_corners(g, inset=90):
    return (inset, g["H"] - inset), (g["W"] - inset, g["H"] - inset)


def party_under(p, g, rnd):
    confetti(p, g, rnd, ["#ffd166", "#4cc9f0", "#ffffff", "#ff9e00"])
    for _ in range(14):
        sparkle(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(10, 22), C("#ffffff", 220))


def party_over(p, g, rnd):
    streamer(p, -20, 60, 260, 0.15, "#ffd166")
    streamer(p, 40, -20, 220, 1.2, "#4cc9f0")
    streamer(p, g["W"] + 20, g["H"] - 70, 260, math.pi + 0.15, "#ffd166")
    streamer(p, g["W"] - 40, g["H"] + 20, 220, math.pi + 1.2, "#4cc9f0")


def geburtstag_under(p, g, rnd):
    confetti(p, g, rnd, ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"], density=12000)


def geburtstag_over(p, g, rnd):
    top = min(b[1] for b in g["photos"])
    flag_h = max(24, min(48, top - 32))
    for x0, x1 in ([(0, g["W"])] if not g["portrait"] else [(0, g["W"] / 2), (g["W"] / 2, g["W"])]):
        bunting(p, x0 + 10, x1 - 10, 6, 20, flag_h, ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"])
    spots = _band_ends(g, 80) if g["band"] and not g["portrait"] else _bottom_corners(g, 70)
    for i, (x, y) in enumerate(spots):
        cols = ["#ff595e", "#1982c4", "#ffca3a"] if i == 0 else ["#8ac926", "#6a4c93", "#ff595e"]
        balloon(p, x - 30, y - 30, 34, cols[0])
        balloon(p, x + 28, y - 44, 30, cols[1])
        balloon(p, x + 2, y + 6, 28, cols[2])


def hochzeit_under(p, g, rnd):
    for _ in range(40):
        heart(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(14, 30), C("#f1c6c0", 200))


def hochzeit_over(p, g, rnd):
    gold = C("#c9a86a")
    gold_border(p, g["W"], g["H"], gold)
    W, H = g["W"], g["H"]
    vine = (C("#b08d57"), C("#9bb59a"), C("#f2b8b5"))
    corner_vine(p, 0, 0, 120, 0.05, math.pi / 2 - 0.05, *vine)
    corner_vine(p, W, 0, 120, math.pi / 2 + 0.05, math.pi - 0.05, *vine)
    corner_vine(p, W, H, 120, math.pi + 0.05, 1.5 * math.pi - 0.05, *vine)
    corner_vine(p, 0, H, 120, 1.5 * math.pi + 0.05, 2 * math.pi - 0.05, *vine)
    if g["band"] and not g["portrait"]:
        (lx, ly), (rx, ry) = _band_ends(g, 110)
        rings(p, lx, ly + 6, 30, C("#c9a86a"))
        heart(p, rx - 18, ry, 50, C("#e5989b"))
        heart(p, rx + 22, ry + 16, 34, C("#f2b8b5"))


def strand_under(p, g, rnd):
    W, H = g["W"], g["H"]
    sand_y = g["band"][1] + 10 if g["band"] else H - 45
    waves(p, W, H, sand_y - 26, 10, 260, C("#90e0ef"), 0.5)
    waves(p, W, H, sand_y - 12, 9, 220, C("#ffffff", 230), 1.7)
    waves(p, W, H, sand_y, 8, 300, C("#f6dcae"), 0.2)
    for _ in range(12):
        x, y = rnd.uniform(0, W), rnd.uniform(sand_y + 25, H)
        p.circle(x, y, rnd.uniform(3, 6), fill=C("#e9c48f"))
    for i in range(3):
        seagull(p, 260 + i * 70, 40 + (i % 2) * 18, 16, C("#1d3557", 200))


def strand_over(p, g, rnd):
    sun(p, g["W"] - 40, 40, 75)
    if not g["portrait"]:  # im Fotostreifen ist neben dem Titel kein Platz für Palmen
        palm(p, 30, g["H"] + 20, 310, 55)
        palm(p, g["W"] - 20, g["H"] + 20, 270, -50)


def urlaub_under(p, g, rnd):
    for _ in range(18):
        x, y = rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"])
        p.circle(x, y, rnd.uniform(40, 90), outline=C("#e9dcc3"), width=2)
    if g["band"] and not g["portrait"]:
        (lx, ly), _ = _band_ends(g, 60)
        dotted_curve(p, [(lx - 40, ly + 45), (lx + 30, ly - 60), (lx + 110, ly - 10)], C("#1d3557", 180), r=3.5)
        plane(p, lx + 125, ly - 8, 42, 0.35, C("#1d3557"))


def urlaub_over(p, g, rnd):
    W, H = g["W"], g["H"]
    airmail_border(p, W, H, 18)
    postmark(p, W - 215, 150, 55, C("#1d3557", 150))
    stamp(p, W - 175, 34, 140, 170, "FERIEN")


def silvester_under(p, g, rnd):
    colors = ["#ffd166", "#f72585", "#4cc9f0", "#ffffff", "#06d6a0"]
    for _ in range(12):
        firework(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(60, 120), rnd.choice(colors), rnd)
    if g["band"]:
        for x, y in _band_ends(g, 90):
            firework(p, x, y, 70, rnd.choice(colors), rnd)
    for _ in range(40):
        sparkle(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(5, 14), C("#ffd166", 220))


def silvester_over(p, g, rnd):
    for x, y in ((40, 40), (g["W"] - 40, 40)):
        sparkle(p, x, y, 34, C("#ffd166"))
        sparkle(p, x + (30 if x < 100 else -30), y + 40, 16, C("#ffffff"))


def weihnachten_under(p, g, rnd):
    for _ in range(55):
        snowflake(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(8, 22), C("#ffffff", 170), 2.5)
    waves(p, g["W"], g["H"], g["H"] - 28, 8, 340, C("#ffffff"))


def weihnachten_over(p, g, rnd):
    spots = _band_ends(g, 80) if g["band"] and not g["portrait"] else _bottom_corners(g, 70)
    for x, y in spots:
        xmas_tree(p, x, y + 70, 150, rnd)
    for x, y in ((45, 45), (g["W"] - 45, 45)):
        star(p, x, y, 28, C("#ffd166"))


def baby_under(p, g, rnd):
    for _ in range(40):
        star(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(6, 14), C("#ffe8a3"))
    for _ in range(7):
        cloud(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(50, 90), C("#ffffff", 220))


def baby_over(p, g, rnd):
    moon(p, g["W"] - 70, 70, 52, C("#ffe8a3"))
    star(p, g["W"] - 150, 45, 14, C("#ffe8a3"))
    spots = _band_ends(g, 90) if g["band"] and not g["portrait"] else _bottom_corners(g, 80)
    for x, y in spots:
        cloud(p, x, y, 70, C("#ffffff"))


def oktoberfest_under(p, g, rnd):
    raute(p, g["W"], g["H"], 64, C("#3d8fd6"))


def oktoberfest_over(p, g, rnd):
    if g["band"] and not g["portrait"]:
        (lx, ly), (rx, ry) = _band_ends(g, 95)
        ginger_heart(p, lx, ly + 4, 140, "Prost!")
        ginger_heart(p, rx, ry + 4, 140, "Servus!")
    else:
        for (x, y), t in zip(_bottom_corners(g, 70), ("Prost!", "Servus!")):
            ginger_heart(p, x, y, 110, t)


def elegant_under(p, g, rnd):
    for _ in range(26):
        sparkle(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(5, 12), C("#d4af37", 200))


def elegant_over(p, g, rnd):
    gold = C("#d4af37")
    gold_border(p, g["W"], g["H"], gold)
    W, H = g["W"], g["H"]
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):  # Art-déco-Ecken
        x0, y0 = (46 if sx > 0 else W - 46), (46 if sy > 0 else H - 46)
        p.line([(x0, y0 + sy * 70), (x0, y0), (x0 + sx * 70, y0)], gold, 3)
        p.line([(x0 + sx * 12, y0 + sy * 40), (x0 + sx * 12, y0 + sy * 12), (x0 + sx * 40, y0 + sy * 12)], gold, 2)


FRAMES = {
    "party": {"label": "Party", "title": "Let's Party!", "bg": ("#3a0ca3", "#f72585"),
              "title_color": "#ffffff", "subtitle_color": "#ffd166", "border": "#ffffff",
              "under": party_under, "over": party_over},
    "geburtstag": {"label": "Geburtstag", "title": "Happy Birthday!", "bg": ("#fff4c9", "#ffd3e2"),
                   "title_color": "#d62f6d", "subtitle_color": "#1982c4", "border": "#ffffff",
                   "under": geburtstag_under, "over": geburtstag_over, "band_pad": 190},
    "hochzeit": {"label": "Hochzeit", "title": "Just Married", "bg": ("#fffaf3", "#f3e6d6"),
                 "title_color": "#5e4b3c", "subtitle_color": "#b08d57", "border": "#ffffff",
                 "under": hochzeit_under, "over": hochzeit_over, "band_pad": 190},
    "strand": {"label": "Strand", "title": "Beach Party", "bg": ("#48cae4", "#caf0f8"),
               "title_color": "#e76f51", "subtitle_color": "#0077b6", "border": "#ffffff",
               "under": strand_under, "over": strand_over, "band_pad": 240},
    "urlaub": {"label": "Urlaub", "title": "Grüsse aus dem Urlaub", "bg": ("#fdf6e7", "#f4e7cf"),
               "title_color": "#1d3557", "subtitle_color": "#d62828", "border": "#ffffff",
               "under": urlaub_under, "over": urlaub_over, "band_pad": 200},
    "silvester": {"label": "Silvester", "title": "Happy New Year!", "bg": ("#1c2541", "#0b132b"),
                  "title_color": "#ffffff", "subtitle_color": "#ffd166", "border": "#d4af37",
                  "under": silvester_under, "over": silvester_over, "band_pad": 170},
    "weihnachten": {"label": "Weihnachten", "title": "Frohe Weihnachten", "bg": ("#ae2012", "#6a040f"),
                    "title_color": "#ffffff", "subtitle_color": "#ffd166", "border": "#ffffff",
                    "under": weihnachten_under, "over": weihnachten_over, "band_pad": 180},
    "baby": {"label": "Baby & Taufe", "title": "Willkommen, kleiner Schatz", "bg": ("#d7efff", "#fde2f3"),
             "title_color": "#6d597a", "subtitle_color": "#e5989b", "border": "#ffffff",
             "under": baby_under, "over": baby_over, "band_pad": 180},
    "oktoberfest": {"label": "Oktoberfest", "title": "O'zapft is!", "bg": ("#ffffff", "#ffffff"),
                    "title_color": "#1f4e8c", "subtitle_color": "#c1121f", "border": "#ffffff",
                    "under": oktoberfest_under, "over": oktoberfest_over, "band_pad": 190,
                    "panel": "#ffffff"},
    "elegant": {"label": "Elegant", "title": "", "bg": ("#14213d", "#000000"),
                "title_color": "#ffffff", "subtitle_color": "#d4af37", "border": "#d4af37",
                "under": elegant_under, "over": elegant_over},
}

NO_FRAME = {"label": "Ohne Rahmen", "title": "", "bg": ("#ffffff", "#ffffff"),
            "title_color": "#2b2d42", "subtitle_color": "#8d99ae", "border": None}


# --------------------------------------------------------------------------- Geometrie
def _geometry(layout_id, has_caption):
    """Positionen der Fotos und des Textbands (Grundgrösse)."""
    if layout_id == "strip":
        W, H = 1200, 1800
        photos, bands = [], []
        for col in (0, 600):  # zwei identische Streifen zum Auseinanderschneiden
            if has_caption:
                photos += [(col + 40, 50 + i * 450, col + 560, 470 + i * 450) for i in range(3)]
                bands.append((col + 20, 1400, col + 580, 1755))
            else:
                photos += [(col + 40, 45 + i * 570, col + 560, 585 + i * 570) for i in range(3)]
        return {"W": W, "H": H, "portrait": True, "photos": photos, "bands": bands,
                "band": bands[0] if bands else None, "copies": 2}
    W, H = 1800, 1200
    if layout_id == "grid":
        h = 455 if has_caption else 530
        photos = [(60 + c * 855, 50 + r * (h + 30), 885 + c * 855, 50 + r * (h + 30) + h)
                  for r in range(2) for c in range(2)]
        band = (60, 1010, 1740, 1185) if has_caption else None
    else:
        photos = [(100, 80, 1700, 960 if has_caption else 1120)]
        band = (100, 975, 1700, 1175) if has_caption else None
    return {"W": W, "H": H, "portrait": False, "photos": photos, "bands": [band] if band else [],
            "band": band, "copies": 1}


# --------------------------------------------------------------------------- Text
def _fit_font(draw, text, font_name, size, max_width, weight=None):
    while size > 10:
        font = _font(font_name, size, weight)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 3
    return _font(font_name, 10, weight)


def _caption(img, k, band, frame, title, date, inline):
    """Titel (Schreibschrift) und Datum ins Band zeichnen; alle Masse in Grundgrösse."""
    d = ImageDraw.Draw(img)
    x1, y1, x2, y2 = band
    pad = frame.get("band_pad", 40) if inline else 30
    cx, cy, width = (x1 + x2) / 2 * k, (y1 + y2) / 2 * k, (x2 - x1 - 2 * pad) * k
    tc, sc = frame["title_color"], frame["subtitle_color"]
    title_size = (100 if inline else 84) * k
    date_size = (54 if inline else 44) * k

    if title and date and inline:
        gap = 45 * k
        date_font = _font("Baloo2.ttf", round(date_size), "Bold")
        date_w = d.textlength(date, font=date_font)
        title_font = _fit_font(d, title, "Pacifico-Regular.ttf", round(title_size), width - date_w - gap)
        title_w = d.textlength(title, font=title_font)
        x = cx - (title_w + gap + date_w) / 2
        d.text((x, cy), title, font=title_font, fill=tc, anchor="lm")
        d.text((x + title_w + gap, cy + 4 * k), date, font=date_font, fill=sc, anchor="lm")
    elif title and date:
        font = _fit_font(d, title, "Pacifico-Regular.ttf", round(title_size), width)
        d.text((cx, y1 * k + (y2 - y1) * k * 0.42), title, font=font, fill=tc, anchor="mm")
        d.text((cx, y1 * k + (y2 - y1) * k * 0.78), date, font=_font("Baloo2.ttf", round(date_size), "Bold"),
               fill=sc, anchor="mm")
    elif title:
        font = _fit_font(d, title, "Pacifico-Regular.ttf", round(title_size), width)
        d.text((cx, cy), title, font=font, fill=tc, anchor="mm")
    elif date:
        d.text((cx, cy), date, font=_font("Baloo2.ttf", round(date_size * 1.3), "Bold"), fill=sc, anchor="mm")


def _overlay_caption(photo, title, date):
    """Einzelbild ohne Rahmen: Titel als Schriftzug unten ins Foto legen."""
    img = photo.copy()
    W, H = img.size
    bar_h = int(H * 0.2)
    shade = Image.linear_gradient("L").resize((W, bar_h)).point(lambda v: int(v * 0.65))
    black = Image.new("RGB", (W, bar_h), "black")
    img.paste(black, (0, H - bar_h), shade)
    frame = {"title_color": "#ffffff", "subtitle_color": "#ffd166", "band_pad": 40}
    k = W / 1800
    _caption(img, k, (0, (H - bar_h * 0.75) / k, 1800, H / k), frame, title, date, inline=True)
    return img


# --------------------------------------------------------------------------- Zusammensetzen
def normalize(design):
    """Einstellungen vereinheitlichen (auch ältere config.json-Dateien)."""
    d = dict(design or {})
    frame = d.get("frame") or LEGACY_FRAMES.get(d.get("theme"), d.get("theme")) or "party"
    d["frame"] = frame if frame in FRAMES or frame == "none" else "party"
    d["layouts"] = list(dict.fromkeys(LEGACY_LAYOUTS.get(l, l) for l in d.get("layouts", LAYOUTS)
                                      if LEGACY_LAYOUTS.get(l, l) in LAYOUTS)) or ["single"]
    default = LEGACY_LAYOUTS.get(d.get("default_layout"), d.get("default_layout"))
    d["default_layout"] = default if default in d["layouts"] else d["layouts"][0]
    d.setdefault("show_title", True)
    d.setdefault("show_date", True)
    d.setdefault("guest_frames", False)
    d.pop("theme", None)
    return d


def _texts(design):
    title = (design.get("frame_text") or "").strip() if design.get("show_title", True) else ""
    date = datetime.date.today().strftime("%d.%m.%Y") if design.get("show_date", True) else ""
    return title, date


def _place(canvas, photo, box, k, frame):
    x1, y1, x2, y2 = [round(v * k) for v in box]
    border = round(12 * k) if frame["border"] else 0
    if frame["border"]:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        off = round(10 * k)
        ImageDraw.Draw(shadow).rectangle((x1 + off, y1 + off * 1.4, x2 + off, y2 + off * 1.4), fill=(0, 0, 0, 105))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, 14 * k)))
        canvas.paste(shadow, (0, 0), shadow)
        ImageDraw.Draw(canvas).rectangle((x1, y1, x2, y2), fill=frame["border"])
    inner = ImageOps.fit(photo, (x2 - x1 - 2 * border, y2 - y1 - 2 * border), Image.LANCZOS)
    canvas.paste(inner, (x1 + border, y1 + border))


def render(layout_id, photos, design, k=1.0):
    """Fertiges Bild (PIL.Image). Bei Einzelbild ohne Rahmen/Text: None (Original verwenden)."""
    design = normalize(design)
    title, date = _texts(design)
    has_caption = bool(title or date)
    frame_id = design["frame"]

    if layout_id == "single" and frame_id == "none":
        if not has_caption:
            return None
        return _overlay_caption(photos[0], title, date)

    frame = FRAMES.get(frame_id, NO_FRAME)
    g = _geometry(layout_id, has_caption)
    size = (round(g["W"] * k), round(g["H"] * k))
    canvas = _gradient(size, *frame["bg"])
    seed = sum(map(ord, frame_id + layout_id))

    if "under" in frame:
        p = Painter(size, k)
        frame["under"](p, g, random.Random(seed))
        layer = p.layer()
        canvas.paste(layer, (0, 0), layer)

    if frame.get("panel"):
        for band in g["bands"]:
            x1, y1, x2, y2 = [v * k for v in band]
            ImageDraw.Draw(canvas).rounded_rectangle((x1, y1, x2, y2), radius=24 * k, fill=frame["panel"],
                                                     outline=frame["title_color"], width=max(1, round(4 * k)))

    for i, box in enumerate(g["photos"]):
        _place(canvas, photos[i % len(photos)], box, k, frame)

    if "over" in frame:
        p = Painter(size, k)
        frame["over"](p, g, random.Random(seed + 1))
        layer = p.layer()
        canvas.paste(layer, (0, 0), layer)

    for band in g["bands"]:
        _caption(canvas, k, band, frame, title, date, inline=not g["portrait"])
    return canvas


def compose(layout_id, photo_paths, design):
    """Bild aus Aufnahmen erstellen – bei Einzelbild ohne Rahmen und ohne Text: None."""
    photos = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in photo_paths]
    return render(layout_id, photos, design)


# --------------------------------------------------------------------------- Vorschau
@functools.lru_cache(maxsize=4)
def placeholder_photos():
    """Beispielbilder für Vorschauen."""
    colors = [("#bde0fe", "#a2d2ff"), ("#ffc8dd", "#ffafcc"), ("#caffbf", "#9bf6ff"), ("#fdffb6", "#ffd6a5")]
    result = []
    for a, b in colors:
        img = _gradient((800, 600), a, b)
        d = ImageDraw.Draw(img)
        d.ellipse((310, 130, 490, 310), fill="#ffffff")
        d.rounded_rectangle((250, 330, 550, 640), radius=120, fill="#ffffff")
        d.arc((360, 200, 440, 270), 20, 160, fill="#555555", width=8)
        d.ellipse((365, 190, 385, 210), fill="#555555")
        d.ellipse((415, 190, 435, 210), fill="#555555")
        result.append(img)
    return tuple(result)


@functools.lru_cache(maxsize=256)
def _preview_cached(layout_id, frame, title, show_title, show_date, date, width):
    design = {"frame": frame, "frame_text": title, "show_title": show_title, "show_date": show_date}
    photos = [ImageOps.fit(ph, (1200, 800)) for ph in placeholder_photos()][:LAYOUTS[layout_id]["shots"]]
    k = min(1.0, width / 1500)
    img = render(layout_id, photos, design, k) or photos[0]
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def preview_jpeg(layout_id, design, width=480):
    d = normalize(design)
    return _preview_cached(layout_id, d["frame"], d.get("frame_text", ""), bool(d["show_title"]),
                           bool(d["show_date"]), datetime.date.today().isoformat(), int(width))


def frame_list():
    return [{"id": "none", "label": NO_FRAME["label"], "title": ""}] + [
        {"id": k, "label": v["label"], "title": v["title"]} for k, v in FRAMES.items()]
