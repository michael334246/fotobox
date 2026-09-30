"""Foto-Layouts und Rahmen: setzt eine oder mehrere Aufnahmen zu einem druckfertigen Bild zusammen.

Alle Layouts ergeben ein 10x15-cm-Bild (Seitenverhältnis 3:2, 300 dpi), damit
sie randlos auf Fotopapier gedruckt werden können. Die Rahmen werden als
Vektorgrafik gezeichnet und sind deshalb in jeder Grösse scharf.

Koordinaten beziehen sich immer auf die Grundgrösse 1800x1200 (bzw. 1200x1800).
Für Vorschaubilder wird mit dem Faktor `k` verkleinert gerendert.

Für die Live-Vorschau beim Fotografieren liefert `overlay_png` den Rahmen als
transparentes PNG, in dem die Fotofelder ausgespart sind.
"""
import datetime
import functools
import io
import json
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

OUTFIT = "Outfit.ttf"
SCRIPT = "GreatVibes-Regular.ttf"


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


def _mesh(size, base, blobs):
    """Weicher «Mesh»-Farbverlauf: unscharfe Farbflächen auf einer Grundfarbe."""
    w, h = max(8, size[0] // 8), max(8, size[1] // 8)
    small = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(small)
    for color, fx, fy, fr in blobs:
        r = fr * max(w, h)
        d.ellipse((fx * w - r, fy * h - r, fx * w + r, fy * h + r), fill=color)
    small = small.filter(ImageFilter.GaussianBlur(max(w, h) * 0.18))
    return small.resize(size, Image.BICUBIC)


class Painter:
    """Zeichenfläche (optional mit Supersampling); Koordinaten in Grundgrösse."""

    def __init__(self, size, k, ss=SS):
        self.size, self.ss = size, ss
        self.f = k * ss
        self.img = Image.new("RGBA", (size[0] * ss, size[1] * ss), (0, 0, 0, 0))
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

    def text(self, xy, text, size, fill, font=OUTFIT, weight="Bold", tracking=0.0):
        _tracked(self.d, (xy[0] * self.f, xy[1] * self.f), text, _font(font, max(6, round(size * self.f)), weight),
                 fill, tracking * size * self.f)

    def layer(self, blur=0.0):
        img = self.img.resize(self.size, Image.LANCZOS) if self.ss > 1 else self.img
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur * self.f / self.ss))
        return img


def _tracked(d, center, text, font, fill, tracking):
    """Text zentriert zeichnen, mit zusätzlichem Buchstabenabstand."""
    if not tracking:
        d.text(center, text, font=font, fill=fill, anchor="mm")
        return
    widths = [d.textlength(ch, font=font) for ch in text]
    x = center[0] - (sum(widths) + tracking * (len(text) - 1)) / 2
    for ch, w in zip(text, widths):
        d.text((x, center[1]), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking


# --------------------------------------------------------------------------- Motive
def confetti(p, g, rnd, colors, density=16000):
    """Moderne Konfetti: Punkte und abgerundete Striche."""
    for _ in range(int(g["W"] * g["H"] / density)):
        x, y = rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"])
        if any(bx1 < x < bx2 and by1 < y < by2 for bx1, by1, bx2, by2 in g["bands"]):
            continue  # Titel frei halten
        color = C(rnd.choice(colors))
        if rnd.random() < 0.5:
            p.circle(x, y, rnd.uniform(4, 8), fill=color)
        else:
            a, length = rnd.uniform(0, math.pi), rnd.uniform(14, 26)
            p.line([(x, y), (x + math.cos(a) * length, y + math.sin(a) * length)], color, 7)


def bokeh(p, g, rnd, colors, count, rmin=12, rmax=60, alpha=(50, 120)):
    for _ in range(count):
        p.circle(rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(rmin, rmax),
                 fill=C(rnd.choice(colors), rnd.randint(*alpha)))


def star(p, cx, cy, r, fill, points=5, inner=0.45, rot=-math.pi / 2):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = rot + i * math.pi / points
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    p.polygon(pts, fill)


def sparkle(p, cx, cy, r, fill):
    star(p, cx, cy, r, fill, points=4, inner=0.2)


def heart(p, cx, cy, s, fill):
    pts = []
    for i in range(72):
        t = i / 72 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s / 34, cy - y * s / 34))
    p.polygon(pts, fill)


def balloon(p, x, y, r, color):
    """Glänzender Ballon mit weicher Schattierung."""
    string = [(x + math.sin(i / 3) * r * 0.1, y + 1.25 * r + i * r * 0.15) for i in range(22)]
    p.line(string, C("#b9b3c9"), 2.5)
    p.polygon([(x - 0.13 * r, y + 1.32 * r), (x + 0.13 * r, y + 1.32 * r), (x, y + 1.14 * r)],
              mix(color, "#000000", 0.15))
    p.ellipse((x - r, y - 1.2 * r, x + r, y + 1.2 * r), fill=mix(color, "#000000", 0.12))
    p.ellipse((x - 0.94 * r, y - 1.18 * r, x + 0.86 * r, y + 1.08 * r), fill=C(color))
    p.ellipse((x - 0.8 * r, y - 1.1 * r, x + 0.5 * r, y + 0.6 * r), fill=mix(color, "#ffffff", 0.18))
    p.ellipse((x - 0.6 * r, y - 0.9 * r, x - 0.25 * r, y - 0.3 * r), fill=mix(color, "#ffffff", 0.7))


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


def branch(p, x, y, angle, length, stem, leaves):
    """Eukalyptus-Zweig: Stiel mit paarweisen ovalen Blättern."""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = [(x + ca * length * t / 20 + math.sin(t / 6) * 10 * -sa, y + sa * length * t / 20 + math.sin(t / 6) * 10 * ca)
           for t in range(21)]
    p.line(pts, stem, 3)
    for i in range(3, 21, 3):
        px, py = pts[i]
        size = 34 * (1.1 - i / 30)
        for side in (-1, 1):
            b = angle + side * 1.0
            cx, cy = px + math.cos(b) * size, py + math.sin(b) * size
            p.ellipse((cx - size * 0.62, cy - size * 0.62, cx + size * 0.62, cy + size * 0.62), fill=leaves[i % 2])


def firework(p, cx, cy, r, color, rnd):
    rays = rnd.randint(18, 26)
    for k in range(rays):
        a = k * 2 * math.pi / rays + rnd.uniform(-0.05, 0.05)
        rr = r * rnd.uniform(0.75, 1.0)
        p.line([(cx + 0.35 * rr * math.cos(a), cy + 0.35 * rr * math.sin(a)),
                (cx + rr * math.cos(a), cy + rr * math.sin(a))], C(color, 210), 2.5)
        p.circle(cx + (rr + 7) * math.cos(a), cy + (rr + 7) * math.sin(a), 3.5, fill=C(color))


def snowflake(p, cx, cy, r, color, width=2.5):
    for k in range(6):
        a = k * math.pi / 3
        p.line([(cx, cy), (cx + r * math.cos(a), cy + r * math.sin(a))], color, width)
        bx, by = cx + 0.6 * r * math.cos(a), cy + 0.6 * r * math.sin(a)
        for s in (-1, 1):
            b = a + s * math.pi / 4
            p.line([(bx, by), (bx + 0.3 * r * math.cos(b), by + 0.3 * r * math.sin(b))], color, width)


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
    (x0, y0), (x1, y1), (x2, y2) = pts
    n = max(2, int((math.hypot(x2 - x0, y2 - y0) + math.hypot(x1 - x0, y1 - y0)) / step))
    for i in range(n):
        t = i / n
        p.circle((1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2,
                 (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2, r, fill=color)


def ginger_heart(p, cx, cy, s, text):
    heart(p, cx, cy, s * 1.08, C("#fff4e0"))
    heart(p, cx, cy, s * 0.98, C("#8b4a2b"))
    for k in range(10):
        a = k * 2 * math.pi / 10
        p.circle(cx + s * 0.34 * math.cos(a), cy - s * 0.02 + s * 0.26 * math.sin(a), s * 0.025,
                 fill=C(["#e63946", "#ffd166", "#06d6a0"][k % 3]))
    p.text((cx, cy - s * 0.05), text, s * 0.17, C("#fff4e0"), weight="ExtraBold")


def raute(p, W, H, d, color):
    for j in range(-1, int(H / (d / 2)) + 2, 2):
        for i in range(-1, int(W / d) + 2):
            cx, cy = i * d, j * d / 2
            p.polygon([(cx, cy - d / 2), (cx + d / 2, cy), (cx, cy + d / 2), (cx - d / 2, cy)], color)


def hairline_frame(p, W, H, color, inset=28):
    p.rect((inset, inset, W - inset, H - inset), outline=color, width=2.5, radius=10)


# --------------------------------------------------------------------------- Rahmen
def _band_ends(g, inset=110):
    x1, y1, x2, y2 = g["band"]
    return (x1 + inset, (y1 + y2) / 2), (x2 - inset, (y1 + y2) / 2)


def _bottom_corners(g, inset=90):
    return (inset, g["H"] - inset), (g["W"] - inset, g["H"] - inset)


def party_glow(p, g, rnd):
    bokeh(p, g, rnd, ["#ffffff", "#7fe7ff", "#ff5fa2", "#8f7bff"], 26, 20, 70, (40, 110))


def party_under(p, g, rnd):
    confetti(p, g, rnd, ["#7fe7ff", "#ff5fa2", "#ffffff", "#ffd166"], density=22000)


def geburtstag_under(p, g, rnd):
    confetti(p, g, rnd, ["#ff4d8d", "#ffb000", "#6c5ce7", "#00b894"])


def geburtstag_over(p, g, rnd):
    spots = _band_ends(g, 85) if g["band"] and not g["portrait"] else _bottom_corners(g, 75)
    for i, (x, y) in enumerate(spots):
        cols = ["#ff4d8d", "#6c5ce7", "#ffb000"] if i == 0 else ["#00b894", "#ff4d8d", "#6c5ce7"]
        balloon(p, x - 30, y - 34, 36, cols[0])
        balloon(p, x + 30, y - 48, 32, cols[1])
        balloon(p, x + 2, y + 4, 29, cols[2])


def hochzeit_over(p, g, rnd):
    W, H = g["W"], g["H"]
    hairline_frame(p, W, H, C("#c8a96a"))
    leaves = (C("#9bb39a"), C("#7f9c7e"))
    branch(p, -10, 110, -0.35, 250, C("#8aa489"), leaves)
    branch(p, 110, -10, 1.95, 220, C("#8aa489"), leaves)
    branch(p, W + 10, H - 110, math.pi - 0.35, 250, C("#8aa489"), leaves)
    branch(p, W - 110, H + 10, -1.2, 220, C("#8aa489"), leaves)


def strand_glow(p, g, rnd):
    p.circle(g["W"] - 110, 70, 160, fill=C("#fff4c2", 170))
    bokeh(p, g, rnd, ["#ffffff"], 14, 10, 40, (40, 90))


def strand_under(p, g, rnd):
    p.circle(g["W"] - 110, 70, 95, fill=C("#fff3c4"))
    y0 = g["H"] - 70
    for i, color in enumerate((C("#ffffff", 190), C("#ffffff", 120))):
        p.line([(x, y0 + i * 26 + 10 * math.sin(x / 90 + i)) for x in range(-20, int(g["W"]) + 40, 20)], color, 4)


def strand_over(p, g, rnd):
    dark, mid = C("#0e5e62", 235), C("#16777b", 235)
    for k, (deg, length) in enumerate(((5, 300), (30, 330), (55, 280), (80, 230))):
        leaf(p, -30, -30, math.radians(deg), length, 46, dark if k % 2 else mid, droop=0.12)
    if not g["portrait"]:
        W, H = g["W"], g["H"]
        for k, (deg, length) in enumerate(((185, 300), (210, 330), (235, 280), (260, 220))):
            leaf(p, W + 30, H + 30, math.radians(deg), length, 46, dark if k % 2 else mid, droop=-0.12)


def urlaub_under(p, g, rnd):
    W = g["W"]
    top = min(b[1] for b in g["photos"])
    dotted_curve(p, [(W * 0.55, top * 0.62), (W * 0.72, 4), (W * 0.9, top * 0.55)], C("#12355b", 150), r=3.5)
    plane(p, W * 0.92, top * 0.5, 24, 0.3, C("#12355b"))


def urlaub_ticket(p, g, rnd):
    """Textband als «Boarding Pass» gestalten."""
    for x1, y1, x2, y2 in g["bands"]:
        p.rect((x1, y1, x2, y2), fill=C("#ffffff"), radius=26)
        if g["portrait"]:
            p.text(((x1 + x2) / 2, y1 + 34), "BOARDING PASS", 20, C("#8aa0b8"), weight="SemiBold", tracking=0.3)
            continue
        sx = x2 - 210
        for y in range(int(y1) + 16, int(y2) - 10, 18):
            p.line([(sx, y), (sx, y + 9)], C("#c6d2de"), 3)
        p.circle(sx, y1, 16, fill=(0, 0, 0, 0))
        p.circle(sx, y2, 16, fill=(0, 0, 0, 0))
        p.text((x1 + 150, y1 + 34), "BOARDING PASS", 20, C("#8aa0b8"), weight="SemiBold", tracking=0.3)
        plane(p, (sx + x2) / 2, (y1 + y2) / 2, 46, -0.5, C("#12355b"))


def silvester_glow(p, g, rnd):
    bokeh(p, g, rnd, ["#f7d774", "#ffffff", "#8f7bff"], 30, 10, 50, (50, 130))


def silvester_under(p, g, rnd):
    colors = ["#f7d774", "#ffffff", "#ff7eb6", "#7fe7ff"]
    for _ in range(8):
        x, y = rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"])
        if not any(bx1 - 110 < x < bx2 + 110 and by1 - 110 < y < by2 + 110 for bx1, by1, bx2, by2 in g["bands"]):
            firework(p, x, y, rnd.uniform(60, 110), rnd.choice(colors), rnd)
    for band in g["bands"]:
        for x, y in _band_ends({"band": band}, 70):
            firework(p, x, y, 55, rnd.choice(colors), rnd)


def weihnachten_glow(p, g, rnd):
    bokeh(p, g, rnd, ["#f2d27a", "#ffffff"], 26, 8, 40, (50, 120))


def weihnachten_under(p, g, rnd):
    for _ in range(40):
        snowflake(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(8, 18), C("#ffffff", 110), 2)


def weihnachten_over(p, g, rnd):
    for x, y in ((48, 48), (g["W"] - 48, 48), (48, g["H"] - 48), (g["W"] - 48, g["H"] - 48)):
        sparkle(p, x, y, 26, C("#f2d27a"))


def baby_glow(p, g, rnd):
    bottom = min(b[1] for b in g["bands"]) - 80 if g["bands"] else g["H"]  # nicht hinter den Titel
    for _ in range(6):
        cloud(p, rnd.uniform(0, g["W"]), rnd.uniform(0, bottom), rnd.uniform(60, 100), C("#ffffff", 230))


def baby_under(p, g, rnd):
    for _ in range(30):
        star(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(6, 12), C("#ffd978"))


def baby_over(p, g, rnd):
    moon(p, g["W"] - 72, 72, 46, C("#ffd978"))
    sparkle(p, g["W"] - 145, 50, 13, C("#ffd978"))


def oktoberfest_under(p, g, rnd):
    raute(p, g["W"], g["H"], 64, C("#8fbfea"))


def oktoberfest_over(p, g, rnd):
    if g["band"] and not g["portrait"]:
        (lx, ly), (rx, ry) = _band_ends(g, 95)
        ginger_heart(p, lx, ly + 4, 140, "Prost!")
        ginger_heart(p, rx, ry + 4, 140, "Servus!")
    else:
        for (x, y), t in zip(_bottom_corners(g, 70), ("Prost!", "Servus!")):
            ginger_heart(p, x, y, 110, t)


def elegant_under(p, g, rnd):
    for _ in range(22):
        sparkle(p, rnd.uniform(0, g["W"]), rnd.uniform(0, g["H"]), rnd.uniform(4, 9), C("#d4af37", 190))


def elegant_over(p, g, rnd):
    gold = C("#d4af37")
    W, H = g["W"], g["H"]
    hairline_frame(p, W, H, gold, 24)
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):  # Art-déco-Ecken
        x0, y0 = (40 if sx > 0 else W - 40), (40 if sy > 0 else H - 40)
        p.line([(x0, y0 + sy * 60), (x0, y0), (x0 + sx * 60, y0)], gold, 3)
        p.circle(x0 + sx * 14, y0 + sy * 14, 4, fill=gold)


# Titel-Schriften
MODERN = {"font": OUTFIT, "weight": "ExtraBold"}
CURSIVE = {"font": SCRIPT, "weight": None, "scale": 1.35}
LUXE = {"font": OUTFIT, "weight": "Light", "upper": True, "tracking": 0.18, "scale": 0.8}

FRAMES = {
    "party": {"label": "Party", "title": "Let's Party!", "base": "#0a0f2c",
              "blobs": [("#ff2e88", 0.05, 0.1, 0.45), ("#2e6bff", 0.95, 0.15, 0.5),
                        ("#00c8ff", 0.8, 1.0, 0.45), ("#7b2ff7", 0.15, 0.95, 0.4)],
              "glow": party_glow, "under": party_under, "title_style": MODERN, "title_glow": "#ff5fa2",
              "title_color": "#ffffff", "subtitle_color": "#7fe7ff", "border": "#ffffff"},
    "geburtstag": {"label": "Geburtstag", "title": "Happy Birthday!", "base": "#fff6ef",
                   "blobs": [("#ffc2a8", 0.0, 0.05, 0.5), ("#ff9ec4", 1.0, 0.1, 0.45),
                             ("#c3b5ff", 0.95, 1.0, 0.5), ("#ffe28a", 0.05, 1.0, 0.45)],
                   "under": geburtstag_under, "over": geburtstag_over, "title_style": MODERN,
                   "title_color": "#ff3d7f", "subtitle_color": "#6c5ce7", "border": "#ffffff", "band_pad": 200},
    "hochzeit": {"label": "Hochzeit", "title": "Just Married", "base": "#fbf7f2",
                 "blobs": [("#f3d5cf", 0.0, 0.0, 0.5), ("#dfe7da", 1.0, 1.0, 0.55), ("#f7e7c6", 1.0, 0.0, 0.35)],
                 "over": hochzeit_over, "title_style": CURSIVE,
                 "title_color": "#6b5641", "subtitle_color": "#b8955a", "border": "#ffffff"},
    "strand": {"label": "Strand", "title": "Beach Party", "base": "#ffb199",
               "blobs": [("#ff8a65", 0.95, 0.0, 0.5), ("#ffcf70", 0.75, 0.25, 0.4), ("#27c3d6", 0.0, 0.95, 0.6),
                         ("#7be0e6", 0.4, 1.05, 0.5), ("#ff6f91", 0.2, 0.05, 0.4)],
               "glow": strand_glow, "under": strand_under, "over": strand_over, "title_style": MODERN,
               "title_glow": "#0e5e62", "title_color": "#ffffff", "subtitle_color": "#ffffff", "border": "#ffffff"},
    "urlaub": {"label": "Urlaub", "title": "Grüsse aus dem Urlaub", "base": "#eaf4ff",
               "blobs": [("#bcdcff", 0.05, 0.1, 0.5), ("#ffd8b8", 0.95, 0.95, 0.45), ("#d7ccff", 0.95, 0.05, 0.35)],
               "under": urlaub_under, "panel_draw": urlaub_ticket, "title_style": MODERN,
               "title_color": "#12355b", "subtitle_color": "#ff6b4a", "border": "#ffffff", "band_pad": 240},
    "silvester": {"label": "Silvester", "title": "Happy New Year!", "base": "#060a1f",
                  "blobs": [("#1d2b6b", 0.15, 0.2, 0.6), ("#3b1d6e", 0.9, 0.85, 0.55), ("#0e3a5c", 0.85, 0.1, 0.4)],
                  "glow": silvester_glow, "under": silvester_under, "title_style": MODERN, "title_glow": "#f7d774",
                  "title_color": "#f7d774", "subtitle_color": "#ffffff", "border": "#f7d774", "band_pad": 170},
    "weihnachten": {"label": "Weihnachten", "title": "Frohe Weihnachten", "base": "#0c3b2e",
                    "blobs": [("#14694e", 0.05, 0.1, 0.55), ("#7a1b2b", 0.95, 0.95, 0.5), ("#0f4d3a", 0.9, 0.1, 0.4)],
                    "glow": weihnachten_glow, "under": weihnachten_under, "over": weihnachten_over,
                    "title_style": CURSIVE, "title_color": "#ffffff", "subtitle_color": "#f2d27a", "border": "#ffffff"},
    "baby": {"label": "Baby & Taufe", "title": "Willkommen, kleiner Schatz", "base": "#f3f8ff",
             "blobs": [("#cfe4ff", 0.05, 0.1, 0.55), ("#ffd5e5", 0.95, 0.95, 0.55), ("#fff0bf", 0.95, 0.05, 0.35)],
             "glow": baby_glow, "under": baby_under, "over": baby_over, "title_style": MODERN,
             "title_color": "#51608f", "subtitle_color": "#e58fb0", "border": "#ffffff"},
    "oktoberfest": {"label": "Oktoberfest", "title": "O'zapft is!", "base": "#ffffff", "blobs": [],
                    "under": oktoberfest_under, "over": oktoberfest_over, "panel": "#ffffff",
                    "title_style": MODERN, "title_color": "#1f4e8c", "subtitle_color": "#c1121f",
                    "border": "#ffffff", "band_pad": 190},
    "elegant": {"label": "Elegant", "title": "", "base": "#0b0b0f", "blobs": [("#1d1d2b", 0.5, 0.5, 0.7)],
                "under": elegant_under, "over": elegant_over, "title_style": LUXE,
                "title_color": "#ffffff", "subtitle_color": "#d4af37", "border": "#d4af37", "border_w": 4},
}

NO_FRAME = {"label": "Ohne Rahmen", "title": "", "base": "#ffffff", "blobs": [], "title_style": MODERN,
            "title_color": "#1d2433", "subtitle_color": "#8a94a6", "border": None}


FONTS = {"modern": MODERN, "script": CURSIVE, "elegant": LUXE}
DEFAULT_BLOBS = [(0.05, 0.1, 0.5), (0.95, 0.95, 0.5), (0.95, 0.05, 0.35)]


def crown(p, cx, cy, s, fill):
    w, h = s * 0.5, s * 0.36
    p.polygon([(cx - w, cy + h), (cx - w, cy - h * 0.2), (cx - w * 0.5, cy + h * 0.25), (cx, cy - h),
               (cx + w * 0.5, cy + h * 0.25), (cx + w, cy - h * 0.2), (cx + w, cy + h)], fill)
    for x in (cx - w, cx, cx + w):
        p.circle(x, cy - (h if x == cx else h * 0.2), s * 0.06, fill=C("#ffffff"))


# Sticker für den Drag-&-Drop-Editor: Name -> Zeichenfunktion (Mittelpunkt, Grösse)
STICKERS = {
    "herz": ("Herz", lambda p, x, y, s: heart(p, x, y, s, C("#ff4d8d"))),
    "stern": ("Stern", lambda p, x, y, s: star(p, x, y, s / 2, C("#ffc93c"))),
    "funkeln": ("Funkeln", lambda p, x, y, s: sparkle(p, x, y, s / 2, C("#ffe28a"))),
    "ballon": ("Ballon", lambda p, x, y, s: balloon(p, x, y - s * 0.15, s * 0.3, "#3b82f6")),
    "krone": ("Krone", lambda p, x, y, s: crown(p, x, y, s, C("#f5c542"))),
    "wolke": ("Wolke", lambda p, x, y, s: cloud(p, x, y - s * 0.1, s * 0.55, C("#ffffff"))),
    "mond": ("Mond", lambda p, x, y, s: moon(p, x, y, s / 2, C("#ffd978"))),
    "flugzeug": ("Flugzeug", lambda p, x, y, s: plane(p, x, y, s / 2, -0.3, C("#12355b"))),
    "lebkuchenherz": ("Lebkuchenherz", lambda p, x, y, s: ginger_heart(p, x, y, s * 0.9, "Prost!")),
}


def effective_frame(frame_id, design):
    """Rahmen mit den Änderungen aus dem Rahmen-Editor (Farben, Schrift, Deko)."""
    base = FRAMES.get(frame_id, NO_FRAME)
    e = (design.get("edits") or {}).get(frame_id) or {}
    f = dict(base)
    if e.get("base"):
        f["base"] = e["base"]
        if not e.get("accents"):  # Akzente zur neuen Grundfarbe hin mischen, damit sie sichtbar wird
            f["blobs"] = [(_hex(mix(b[0], e["base"], 0.6)),) + tuple(b[1:]) for b in base["blobs"]]
    if e.get("accents"):
        spots = [b[1:] for b in base["blobs"]] + DEFAULT_BLOBS[len(base["blobs"]):]
        f["blobs"] = [(c,) + tuple(spot) for c, spot in zip(e["accents"], spots) if c]
    for key in ("title_color", "subtitle_color"):
        if e.get(key):
            f[key] = e[key]
    if "border" in e:
        f["border"] = e["border"] or None
    if e.get("font") in FONTS:
        f["title_style"] = FONTS[e["font"]]
        f.pop("title_glow", None)
    f["title_scale"] = float(e.get("title_scale") or 1)
    if e.get("decor") is False:
        for key in ("glow", "under", "over", "panel_draw", "title_glow"):
            f.pop(key, None)
    return f


def _hex(rgba):
    return "#%02x%02x%02x" % tuple(rgba[:3])


def frame_style(frame_id, design):
    """Aktuelle Werte eines Rahmens für den Editor."""
    f = effective_frame(frame_id, design)
    base = FRAMES.get(frame_id, NO_FRAME)
    font = next((k for k, v in FONTS.items() if v is f["title_style"]), "modern")
    e = (design.get("edits") or {}).get(frame_id) or {}
    return {"base": f["base"], "accents": [b[0] for b in f["blobs"]][:3],
            "title_color": f["title_color"], "subtitle_color": f["subtitle_color"],
            "border": f["border"] or "", "font": font, "title_scale": f["title_scale"],
            "decor": e.get("decor", True), "has_decor": any(k in base for k in ("glow", "under", "over"))}


# --------------------------------------------------------------------------- Geometrie
def _geometry(layout_id, has_caption):
    """Positionen der Fotos und der Textbänder (Grundgrösse)."""
    if layout_id == "strip":
        photos, bands = [], []
        for col in (0, 600):  # zwei identische Streifen zum Auseinanderschneiden
            if has_caption:
                photos += [(col + 40, 50 + i * 450, col + 560, 470 + i * 450) for i in range(3)]
                bands.append((col + 30, 1400, col + 570, 1750))
            else:
                photos += [(col + 40, 45 + i * 570, col + 560, 585 + i * 570) for i in range(3)]
        return {"W": 1200, "H": 1800, "portrait": True, "photos": photos, "bands": bands,
                "band": bands[0] if bands else None, "copies": 2, "cell_w": 600}
    if layout_id == "grid":
        h = 445 if has_caption else 520
        photos = [(60 + c * 855, 55 + r * (h + 30), 885 + c * 855, 55 + r * (h + 30) + h)
                  for r in range(2) for c in range(2)]
        band = (60, 1000, 1740, 1170) if has_caption else None
    else:
        photos = [(90, 80, 1710, 955 if has_caption else 1120)]
        band = (90, 975, 1710, 1170) if has_caption else None
    return {"W": 1800, "H": 1200, "portrait": False, "photos": photos, "bands": [band] if band else [],
            "band": band, "copies": 1, "cell_w": 1800}


def _inner(box, frame):
    b = frame.get("border_w", 10) if frame["border"] else 0
    x1, y1, x2, y2 = box
    return (x1 + b, y1 + b, x2 - b, y2 - b), max(6, 22 - b)


# --------------------------------------------------------------------------- Text
def _fit_font(draw, text, font_name, size, max_width, weight=None):
    while size > 10:
        font = _font(font_name, size, weight)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 3
    return _font(font_name, 10, weight)


def _caption(img, k, band, frame, title, date, portrait):
    """Titel und Datum zentriert ins Band zeichnen; Masse in Grundgrösse."""
    d = ImageDraw.Draw(img)
    x1, y1, x2, y2 = band
    pad = 30 if portrait else frame.get("band_pad", 60)
    cx, width, h = (x1 + x2) / 2 * k, (x2 - x1 - 2 * pad) * k, (y2 - y1) * k
    style = frame["title_style"]
    if style.get("upper"):
        title = title.upper()
    size = round((74 if portrait else 88) * style.get("scale", 1) * frame.get("title_scale", 1) * k)
    date_size = round((28 if portrait else 32) * k)

    title_y = y1 * k + h * (0.4 if date else 0.5)
    date_y = y1 * k + h * (0.84 if title else 0.5)
    if title:
        font = _fit_font(d, title, style["font"], size, width, style.get("weight"))
        tracking = style.get("tracking", 0) * font.size
        if frame.get("title_glow"):
            glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            _tracked(ImageDraw.Draw(glow), (cx, title_y), title, font, C(frame["title_glow"], 200), tracking)
            glow = glow.filter(ImageFilter.GaussianBlur(max(1, 14 * k)))
            if img.mode == "RGBA":
                img.alpha_composite(glow)
            else:
                img.paste(glow, (0, 0), glow)
        _tracked(d, (cx, title_y), title, font, frame["title_color"], tracking)
    if date:
        font = _font(OUTFIT, date_size if title else round(date_size * 1.6), "Medium")
        _tracked(d, (cx, date_y), date, font, frame["subtitle_color"], 0.3 * font.size)


# --------------------------------------------------------------------------- Einstellungen
def normalize(design):
    """Einstellungen vereinheitlichen (auch ältere config.json-Dateien)."""
    d = dict(design or {})
    frame = d.get("frame") or LEGACY_FRAMES.get(d.get("theme"), d.get("theme")) or "party"
    d["frame"] = frame if frame in FRAMES or frame == "none" else "party"
    d.setdefault("custom_frames", [])
    valid = set(LAYOUTS) | {c["id"] for c in d["custom_frames"]}
    d["layouts"] = list(dict.fromkeys(LEGACY_LAYOUTS.get(l, l) for l in d.get("layouts", LAYOUTS)
                                      if LEGACY_LAYOUTS.get(l, l) in valid)) or ["single"]
    default = LEGACY_LAYOUTS.get(d.get("default_layout"), d.get("default_layout"))
    d["default_layout"] = default if default in d["layouts"] else d["layouts"][0]
    d.setdefault("show_title", True)
    d.setdefault("show_date", True)
    d.setdefault("guest_frames", False)
    d.setdefault("edits", {})
    d.setdefault("logo", {})
    d.pop("theme", None)
    return d


def layout_list(design):
    """Alle Layouts inkl. eigener Rahmen: [{id, label, shots}]."""
    d = normalize(design)
    items = [{"id": k, "label": v["label"], "shots": v["shots"]} for k, v in LAYOUTS.items()]
    items += [{"id": c["id"], "label": c["name"], "shots": len(c["holes"]), "custom": True}
              for c in d["custom_frames"]]
    return items


def _custom(design, layout_id):
    return next((c for c in design.get("custom_frames", []) if c["id"] == layout_id), None)


def _texts(design):
    title = (design.get("frame_text") or "").strip() if design.get("show_title", True) else ""
    date = datetime.date.today().strftime("%d.%m.%Y") if design.get("show_date", True) else ""
    return title, date


def _edit_key(layout_id, design):
    """Unter diesem Namen speichert der Editor Positionen: eigener Rahmen oder gewählter Rahmen."""
    return layout_id if _custom(design, layout_id) else design["frame"]


def positions(layout_id, design):
    """Frei platzierte Elemente aus dem Drag-&-Drop-Editor (Anteile der Zelle)."""
    e = (design.get("edits") or {}).get(_edit_key(layout_id, design)) or {}
    return (e.get("pos") or {}).get(layout_id) or {}


# --------------------------------------------------------------------------- Eigene Rahmen
def detect_holes(img):
    """Durchsichtige Fotofenster eines PNG-Rahmens finden (Begrenzungsrechtecke, Lesereihenfolge)."""
    alpha = img.getchannel("A")
    step = max(1, max(img.size) // 300)
    w, h = img.width // step, img.height // step
    small = alpha.resize((w, h), Image.NEAREST).load()
    seen = [[False] * w for _ in range(h)]
    holes = []
    for y0 in range(h):
        for x0 in range(w):
            if seen[y0][x0] or small[x0, y0] >= 32:
                continue
            stack, area = [(x0, y0)], 0
            seen[y0][x0] = True
            x1, y1, x2, y2 = x0, y0, x0, y0
            while stack:
                x, y = stack.pop()
                area += 1
                x1, y1, x2, y2 = min(x1, x), min(y1, y), max(x2, x), max(y2, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and small[nx, ny] < 32:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if area > w * h * 0.015:  # etwas grösser, damit keine Lücke bleibt (der Rahmen deckt den Rand ab)
                holes.append([max(0, (x1 - 1) * step), max(0, (y1 - 1) * step),
                              min(img.width, (x2 + 2) * step), min(img.height, (y2 + 2) * step)])
    row = img.height * 0.1
    return sorted(holes, key=lambda b: (round(b[1] / row), b[0]))


# --------------------------------------------------------------------------- Zeichnen
def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _place(canvas, photo, box, k, frame):
    """Foto mit abgerundeten Ecken, Rand und weichem Schatten einsetzen.
    Ohne Foto (photo=None) wird das Feld transparent ausgespart."""
    x1, y1, x2, y2 = [round(v * k) for v in box]
    (ix1, iy1, ix2, iy2), inner_r = _inner(box, frame)
    ix1, iy1, ix2, iy2 = [round(v * k) for v in (ix1, iy1, ix2, iy2)]
    radius = round(22 * k)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    off = round(12 * k)
    ImageDraw.Draw(shadow).rounded_rectangle((x1, y1 + off, x2, y2 + off), radius=radius, fill=(0, 0, 0, 80))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(1, 20 * k))))
    if frame["border"]:
        ImageDraw.Draw(canvas).rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=frame["border"])
    size = (ix2 - ix1, iy2 - iy1)
    mask = _rounded_mask(size, round(inner_r * k))
    if photo is None:
        canvas.paste(Image.new("RGBA", size, (0, 0, 0, 0)), (ix1, iy1), mask)
    else:
        canvas.paste(ImageOps.fit(photo, size, Image.LANCZOS), (ix1, iy1), mask)


def _layer(canvas, fn, g, size, k, seed, ss=SS, blur=0.0):
    p = Painter(size, k, ss)
    fn(p, g, random.Random(seed))
    canvas.alpha_composite(p.layer(blur))


def _caption_bar(canvas, k, g, title, date):
    """«Ohne Rahmen»: Schriftzug auf dunklem Verlauf unten im Bild."""
    W, H = canvas.size
    bar_h = int(H * 0.24)
    shade = Image.linear_gradient("L").resize((W, bar_h)).point(lambda v: int(v * 0.7))
    canvas.paste(Image.new("RGBA", (W, bar_h), "black"), (0, H - bar_h), shade)
    frame = dict(NO_FRAME, title_color="#ffffff", subtitle_color="#dbe7ff", band_pad=60)
    _caption(canvas, k, (0, g["H"] - bar_h * 0.85 / k, g["W"], g["H"]), frame, title, date, portrait=False)


def _draw_text(canvas, k, xy, text, style, color, size, glow=None):
    d = ImageDraw.Draw(canvas)
    if style.get("upper"):
        text = text.upper()
    font = _font(style["font"], max(8, round(size * k)), style.get("weight"))
    tracking = style.get("tracking", 0) * font.size
    center = (xy[0] * k, xy[1] * k)
    if glow:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        _tracked(ImageDraw.Draw(layer), center, text, font, C(glow, 200), tracking)
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(max(1, 14 * k))))
    _tracked(d, center, text, font, color, tracking)


def _logo_box(g, pos, logo, logo_opts):
    """Mittelpunkt und Breite des Logos (Grundgrösse, bezogen auf die erste Zelle)."""
    cw, H = g["cell_w"], g["H"]
    if "logo" in pos:
        x, y, s = pos["logo"]
        return x * cw, y * H, s * cw
    width = float(logo_opts.get("size") or 0.18) * cw
    height = width * logo.height / logo.width
    m = 0.035 * max(cw, H)
    corner = logo_opts.get("position") or "br"
    x = m + width / 2 if corner[1] == "l" else cw - m - width / 2
    y = m + height / 2 if corner[0] == "t" else H - m - height / 2
    return x, y, width


def _extras(canvas, k, g, design, layout_id, frame, title, date, default_caption, fallback_pos=None):
    """Titel/Datum, Logo und Sticker – je Zelle (Fotostreifen: zweimal)."""
    pos = positions(layout_id, design) or fallback_pos or {}
    logo_opts = design.get("logo") or {}
    logo = None
    if logo_opts.get("enabled") and design.get("logo_path") and os.path.exists(design["logo_path"]):
        logo = Image.open(design["logo_path"]).convert("RGBA")

    for copy in range(g["copies"]):
        dx = copy * g["cell_w"]
        if "title" in pos or "date" in pos:
            if title and "title" in pos:
                x, y, sz = pos["title"]
                _draw_text(canvas, k, (dx + x * g["cell_w"], y * g["H"]), title, frame["title_style"],
                           frame["title_color"], sz * g["H"], frame.get("title_glow"))
            if date and "date" in pos:
                x, y, sz = pos["date"]
                _draw_text(canvas, k, (dx + x * g["cell_w"], y * g["H"]), date,
                           {"font": OUTFIT, "weight": "Medium", "tracking": 0.3}, frame["subtitle_color"], sz * g["H"])
        elif default_caption and (title or date):
            default_caption(copy)

        stickers = pos.get("stickers") or []
        if stickers:
            p = Painter(canvas.size, k)
            for kind, x, y, sz in stickers:
                if kind in STICKERS:
                    STICKERS[kind][1](p, dx + x * g["cell_w"], y * g["H"], sz * g["H"])
            canvas.alpha_composite(p.layer())

        if logo:
            x, y, w = _logo_box(g, pos, logo, logo_opts)
            size = (max(1, round(w * k)), max(1, round(w * k * logo.height / logo.width)))
            img = logo.resize(size, Image.LANCZOS)
            canvas.alpha_composite(img, (round((dx + x) * k - size[0] / 2), round(y * k - size[1] / 2)))


def _has_extras(layout_id, design, title, date):
    pos = positions(layout_id, design)
    return bool(title or date or pos.get("stickers") or (design.get("logo") or {}).get("enabled"))


# --------------------------------------------------------------------------- Zusammensetzen
def render(layout_id, photos, design, k=1.0, overlay=False, extras=True):
    """Fertiges Bild (PIL.Image) oder – mit overlay=True – der Rahmen mit transparenten Fotofeldern.

    extras=False lässt Titel, Datum, Logo und Sticker weg (Hintergrund für den Editor).
    Einzelbild ohne Rahmen und ohne Zusätze: None (Original verwenden bzw. keine Maske nötig).
    """
    design = normalize(design)
    title, date = _texts(design)
    custom = _custom(design, layout_id)

    if custom:
        return _render_custom(custom, photos, design, k, overlay, extras, title, date)
    if layout_id == "single" and design["frame"] == "none":
        return _render_plain(photos, design, k, overlay, extras, title, date)

    frame = effective_frame(design["frame"], design)
    g = _geometry(layout_id, bool(title or date))
    size = (round(g["W"] * k), round(g["H"] * k))
    canvas = _mesh(size, frame["base"], frame["blobs"]).convert("RGBA")
    seed = sum(map(ord, design["frame"] + layout_id))

    if "glow" in frame:  # weiche, unscharfe Lichtpunkte
        _layer(canvas, frame["glow"], g, size, k, seed, ss=1, blur=10)
    if "under" in frame:
        _layer(canvas, frame["under"], g, size, k, seed + 1)
    if frame.get("panel"):
        for x1, y1, x2, y2 in g["bands"]:
            ImageDraw.Draw(canvas).rounded_rectangle([v * k for v in (x1, y1, x2, y2)], radius=26 * k,
                                                     fill=frame["panel"], outline=frame["title_color"],
                                                     width=max(1, round(3 * k)))
    if "panel_draw" in frame and g["bands"]:
        _layer(canvas, frame["panel_draw"], g, size, k, seed + 2)

    for i, box in enumerate(g["photos"]):
        _place(canvas, None if overlay else photos[i % len(photos)], box, k, frame)

    if "over" in frame:
        _layer(canvas, frame["over"], g, size, k, seed + 3)
    if extras:
        _extras(canvas, k, g, design, layout_id, frame, title, date,
                lambda copy: _caption(canvas, k, g["bands"][copy], frame, title, date, g["portrait"]))
    return canvas if overlay else canvas.convert("RGB")


def _render_plain(photos, design, k, overlay, extras, title, date):
    """Einzelbild ohne Rahmen: Originalfoto, Zusätze direkt darauf."""
    if not extras or not _has_extras("single", design, title, date):
        return None
    if overlay:
        canvas = Image.new("RGBA", (round(1800 * k), round(1200 * k)), (0, 0, 0, 0))
    else:
        canvas = photos[0].convert("RGBA")
        k = canvas.width / 1800
    g = {"W": 1800, "H": canvas.height / k, "copies": 1, "cell_w": 1800, "portrait": False}
    # Text liegt direkt auf dem Foto: ohne Änderung im Editor weiss
    edits = design["edits"].get("none") or {}
    frame = dict(effective_frame("none", design), title_color=edits.get("title_color") or "#ffffff",
                 subtitle_color=edits.get("subtitle_color") or "#dbe7ff")
    _extras(canvas, k, g, design, "single", frame, title, date, lambda copy: _caption_bar(canvas, k, g, title, date))
    return canvas if overlay else canvas.convert("RGB")


def _render_custom(custom, photos, design, k, overlay, extras, title, date):
    """Eigener PNG-Rahmen: Fotos unter die durchsichtigen Fenster legen."""
    png = Image.open(custom["path"]).convert("RGBA")
    W, H = custom["size"]
    size = (round(W * k), round(H * k))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0) if overlay else (255, 255, 255, 255))
    if not overlay:
        for i, (x1, y1, x2, y2) in enumerate(custom["holes"]):
            box = [round(v * k) for v in (x1, y1, x2, y2)]
            canvas.paste(ImageOps.fit(photos[i % len(photos)], (box[2] - box[0], box[3] - box[1]), Image.LANCZOS),
                         box[:2])
    canvas.alpha_composite(png.resize(size, Image.LANCZOS))
    if extras:
        g = {"W": W, "H": H, "copies": 1, "cell_w": W, "portrait": H > W}
        frame = dict(NO_FRAME, **{k2: v for k2, v in effective_frame(custom["id"], design).items()
                                  if k2 in ("title_color", "subtitle_color", "title_style", "title_scale")})
        _extras(canvas, k, g, design, custom["id"], frame, title, date, None,
                default_positions(custom["id"], design))
    return canvas if overlay else canvas.convert("RGB")


def compose(layout_id, photo_paths, design):
    """Bild aus Aufnahmen erstellen – bei Einzelbild ohne Rahmen und ohne Zusätze: None."""
    photos = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in photo_paths]
    return render(layout_id, photos, design)


def _cache_key(layout_id, design, *extra):
    d = normalize(design)
    return (layout_id, json.dumps(d, sort_keys=True, default=str), datetime.date.today().isoformat()) + extra


# --------------------------------------------------------------------------- Live-Vorschau
def overlay_info(layout_id, design):
    """Maße und Fotofelder der Live-Vorschau (Grundgrösse)."""
    d = normalize(design)
    title, date = _texts(d)
    custom = _custom(d, layout_id)
    if custom:
        return {"size": custom["size"], "holes": [h + [0] for h in custom["holes"]], "overlay": True}
    if layout_id == "single" and d["frame"] == "none":
        return {"size": [1800, 1200], "holes": [[0, 0, 1800, 1200, 0]],
                "overlay": _has_extras("single", d, title, date)}
    frame = effective_frame(d["frame"], d)
    g = _geometry(layout_id, bool(title or date))
    holes = []
    for box in g["photos"]:
        inner, r = _inner(box, frame)
        holes.append(list(inner) + [r])
    return {"size": [g["W"], g["H"]], "holes": holes, "overlay": True}


@functools.lru_cache(maxsize=32)
def _overlay_cached(key):
    layout_id, design_json = key[0], key[1]
    img = render(layout_id, None, json.loads(design_json), k=0.6, overlay=True)
    if img is None:  # nichts über dem Kamerabild
        img = Image.new("RGBA", (1080, 720), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def overlay_png(layout_id, design):
    return _overlay_cached(_cache_key(layout_id, design))


# --------------------------------------------------------------------------- Vorschau
@functools.lru_cache(maxsize=4)
def placeholder_photos():
    """Beispielbilder für Vorschauen."""
    colors = [("#bde0fe", "#a2d2ff"), ("#ffc8dd", "#ffafcc"), ("#caffbf", "#9bf6ff"), ("#fdffb6", "#ffd6a5")]
    result = []
    for a, b in colors:
        img = _mesh((800, 600), a, [(b, 0.8, 0.9, 0.6)])
        d = ImageDraw.Draw(img)
        d.ellipse((310, 130, 490, 310), fill="#ffffff")
        d.rounded_rectangle((250, 330, 550, 640), radius=120, fill="#ffffff")
        d.arc((360, 200, 440, 270), 20, 160, fill="#555555", width=8)
        d.ellipse((365, 190, 385, 210), fill="#555555")
        d.ellipse((415, 190, 435, 210), fill="#555555")
        result.append(img)
    return tuple(result)


@functools.lru_cache(maxsize=256)
def _preview_cached(key, width, extras):
    layout_id, design = key[0], json.loads(key[1])
    shots = next(l["shots"] for l in layout_list(design) if l["id"] == layout_id)
    photos = [ImageOps.fit(ph, (1200, 800)) for ph in placeholder_photos()] * 3
    img = render(layout_id, photos[:shots], design, min(1.0, width / 1500), extras=extras) or photos[0]
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def preview_jpeg(layout_id, design, width=480, extras=True):
    return _preview_cached(_cache_key(layout_id, design), int(width), extras)


def editor_background(layout_id, design, width=900):
    """Rahmen ohne Titel/Logo/Sticker, nur die erste Zelle (Fotostreifen: ein Streifen)."""
    img = Image.open(io.BytesIO(preview_jpeg(layout_id, design, width, extras=False)))
    d = normalize(design)
    if layout_id == "strip" and not _custom(d, layout_id):
        img = img.crop((0, 0, img.width // 2, img.height))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def default_positions(layout_id, design):
    """Startpositionen für den Drag-&-Drop-Editor (Anteile der Zelle)."""
    d = normalize(design)
    custom = _custom(d, layout_id)
    title_size = 0.07
    if custom:
        return {"title": [0.5, 0.9, title_size], "date": [0.5, 0.96, 0.028], "stickers": []}
    if layout_id == "single" and d["frame"] == "none":
        return {"title": [0.5, 0.86, title_size], "date": [0.5, 0.94, 0.028], "stickers": []}
    g = _geometry(layout_id, True)
    x1, y1, x2, y2 = g["band"]
    h, cw = y2 - y1, g["cell_w"]
    frame = effective_frame(d["frame"], d)
    size = (74 if g["portrait"] else 88) * frame["title_style"].get("scale", 1) * frame.get("title_scale", 1)
    return {"title": [(x1 + x2) / 2 / cw, (y1 + h * 0.4) / g["H"], size / g["H"]],
            "date": [(x1 + x2) / 2 / cw, (y1 + h * 0.84) / g["H"], (28 if g["portrait"] else 32) / g["H"]],
            "stickers": []}


@functools.lru_cache(maxsize=32)
def sticker_png(kind, size=160):
    p = Painter((size, size), size / 200)
    STICKERS[kind][1](p, 100, 100, 150)
    buf = io.BytesIO()
    p.layer().save(buf, format="PNG")
    return buf.getvalue()


def frame_list():
    return [{"id": "none", "label": NO_FRAME["label"], "title": ""}] + [
        {"id": k, "label": v["label"], "title": v["title"]} for k, v in FRAMES.items()]
