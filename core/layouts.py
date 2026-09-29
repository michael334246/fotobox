"""Foto-Layouts: setzt eine oder mehrere Aufnahmen zu einem druckfertigen Bild zusammen.

Alle Layouts ergeben ein 10x15-cm-Bild (Seitenverhältnis 3:2, 300 dpi), damit
sie randlos auf Fotopapier gedruckt werden können.
"""
import datetime
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")

LAYOUTS = {
    "classic": {"label": "Klassisch", "shots": 1, "size": (1800, 1200)},
    "polaroid": {"label": "Mit Rahmen", "shots": 1, "size": (1800, 1200)},
    "strip": {"label": "Fotostreifen", "shots": 3, "size": (1200, 1800)},
    "grid": {"label": "4er-Collage", "shots": 4, "size": (1800, 1200)},
}

THEMES = {
    "party": {
        "label": "Party (Violett/Pink)",
        "bg": ("#3a0ca3", "#f72585"),
        "confetti": ["#ffd166", "#4cc9f0", "#ffffff", "#ff9e00"],
        "title": "#ffffff",
        "subtitle": "#ffd166",
        "border": "#ffffff",
    },
    "bunt": {
        "label": "Bunt (Sonnengelb)",
        "bg": ("#ffd166", "#ff8c42"),
        "confetti": ["#f72585", "#3a0ca3", "#4cc9f0", "#ffffff"],
        "title": "#3a0ca3",
        "subtitle": "#ffffff",
        "border": "#ffffff",
    },
    "elegant": {
        "label": "Elegant (Hochzeit)",
        "bg": ("#fffaf2", "#f3e7d3"),
        "confetti": [],
        "title": "#3b3024",
        "subtitle": "#b08d57",
        "border": "#ffffff",
        "line": "#c9a86a",
    },
    "nacht": {
        "label": "Nacht (Schwarz/Gold)",
        "bg": ("#1a1a1a", "#000000"),
        "confetti": ["#d4af37", "#f5e6a8"],
        "title": "#ffffff",
        "subtitle": "#d4af37",
        "border": "#d4af37",
    },
}


# --------------------------------------------------------------------------- Hilfsfunktionen
def _font(name, size, weight=None):
    try:
        font = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        if weight:
            font.set_variation_by_name(weight)
        return font
    except (OSError, ValueError):
        return ImageFont.load_default(size=size)


def _background(size, theme, seed):
    top, bottom = theme["bg"]
    mask = Image.linear_gradient("L").resize(size)
    img = Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)

    if theme["confetti"]:
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        rnd = random.Random(seed)
        w, h = size
        for _ in range(int(w * h / 9000)):
            x, y = rnd.randint(0, w), rnd.randint(0, h)
            r = rnd.randint(4, 14)
            color = rnd.choice(theme["confetti"])
            alpha = rnd.randint(90, 220)
            fill = Image.new("RGB", (1, 1), color).getpixel((0, 0)) + (alpha,)
            if rnd.random() < 0.5:
                d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
            else:
                d.rounded_rectangle((x - r, y - r // 2, x + r, y + r // 2), radius=3, fill=fill)
        img.paste(layer, (0, 0), layer)
    return img


def _place_photo(canvas, photo, box, theme, border=10):
    """Bild zugeschnitten in `box` einsetzen, mit Rand und weichem Schatten."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((x1 + 8, y1 + 14, x2 + 8, y2 + 14), fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.paste(shadow, (0, 0), shadow)

    ImageDraw.Draw(canvas).rectangle(box, fill=theme["border"])
    inner = ImageOps.fit(photo, (w - 2 * border, h - 2 * border), Image.LANCZOS)
    canvas.paste(inner, (x1 + border, y1 + border))


def _text(canvas, center, text, font_name, max_size, max_width, color, weight=None):
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    font = _fit_font(d, text, font_name, max_size, max_width, weight)
    d.text(center, text, font=font, fill=color, anchor="mm")


def _fit_font(draw, text, font_name, max_size, max_width, weight=None):
    size = max_size
    while True:
        font = _font(font_name, size, weight)
        if size <= 16 or draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4


def _caption(canvas, area, design, theme, title_size, date_size, inline=False):
    """Anlassname und Datum in `area` = (x1, y1, x2, y2): untereinander oder nebeneinander."""
    x1, y1, x2, y2 = area
    cx, cy, width = (x1 + x2) // 2, (y1 + y2) // 2, (x2 - x1) - 40
    d = ImageDraw.Draw(canvas)
    title = design.get("frame_text", "")
    date = datetime.date.today().strftime("%d.%m.%Y") if design.get("show_date", True) else ""

    if "line" in theme and (title or date):
        d.line((cx - 160, y1 + 4, cx + 160, y1 + 4), fill=theme["line"], width=3)

    if title and date and inline:
        gap = 50
        date_font = _font("Baloo2.ttf", date_size, "Bold")
        date_w = d.textlength(date, font=date_font)
        title_font = _fit_font(d, title, "Pacifico-Regular.ttf", title_size, width - date_w - gap)
        title_w = d.textlength(title, font=title_font)
        x = cx - (title_w + gap + date_w) / 2
        d.text((x, cy), title, font=title_font, fill=theme["title"], anchor="lm")
        d.text((x + title_w + gap, cy + 4), date, font=date_font, fill=theme["subtitle"], anchor="lm")
    elif title and date:
        _text(canvas, (cx, y1 + (y2 - y1) * 0.40), title, "Pacifico-Regular.ttf", title_size, width, theme["title"])
        _text(canvas, (cx, y1 + (y2 - y1) * 0.78), date, "Baloo2.ttf", date_size, width,
              theme["subtitle"], "Bold")
    elif title:
        _text(canvas, (cx, cy), title, "Pacifico-Regular.ttf", title_size, width, theme["title"])
    elif date:
        _text(canvas, (cx, cy), date, "Baloo2.ttf", date_size, width, theme["subtitle"], "Bold")


# --------------------------------------------------------------------------- Layouts
def _polaroid(photos, design, theme, size):
    canvas = _background(size, theme, 1)
    _place_photo(canvas, photos[0], (70, 60, 1730, 994), theme, border=14)
    _caption(canvas, (70, 1004, 1730, 1190), design, theme, 100, 56, inline=True)
    return canvas


def _strip(photos, design, theme, size):
    canvas = _background(size, theme, 2)
    for col in (0, 600):  # zwei identische Streifen zum Auseinanderschneiden
        for i, photo in enumerate(photos[:3]):
            y = 50 + i * 450
            _place_photo(canvas, photo, (col + 40, y, col + 560, y + 420), theme)
        _caption(canvas, (col + 20, 1400, col + 580, 1750), design, theme, 84, 44)
    if theme is THEMES.get("elegant"):
        ImageDraw.Draw(canvas).line((600, 0, 600, size[1]), fill="#e6dccb", width=2)
    return canvas


def _grid(photos, design, theme, size):
    canvas = _background(size, theme, 3)
    for i, photo in enumerate(photos[:4]):
        col, row = i % 2, i // 2
        x, y = 60 + col * 855, 50 + row * 480
        _place_photo(canvas, photo, (x, y, x + 825, y + 460), theme)
    _caption(canvas, (60, 1015, 1740, 1190), design, theme, 96, 54, inline=True)
    return canvas


RENDERERS = {"polaroid": _polaroid, "strip": _strip, "grid": _grid}


def compose(layout_id, photo_paths, design):
    """Gibt das fertige Bild zurück (PIL.Image) – bei «classic» None (Original verwenden)."""
    layout = LAYOUTS[layout_id]
    if layout_id == "classic":
        return None
    theme = THEMES.get(design.get("theme"), THEMES["party"])
    photos = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in photo_paths]
    return RENDERERS[layout_id](photos, design, theme, layout["size"])


def placeholder_photos(count):
    """Beispielbilder für die Vorschau in der Layout-Auswahl."""
    colors = [("#bde0fe", "#a2d2ff"), ("#ffc8dd", "#ffafcc"), ("#caffbf", "#9bf6ff"), ("#fdffb6", "#ffd6a5")]
    result = []
    for i in range(count):
        a, b = colors[i % len(colors)]
        img = Image.composite(Image.new("RGB", (800, 600), b), Image.new("RGB", (800, 600), a),
                              Image.linear_gradient("L").resize((800, 600)))
        d = ImageDraw.Draw(img)
        d.ellipse((310, 130, 490, 310), fill="#ffffff")            # Kopf
        d.rounded_rectangle((250, 330, 550, 640), radius=120, fill="#ffffff")  # Körper
        d.arc((360, 200, 440, 270), 20, 160, fill="#555555", width=8)          # Lächeln
        d.ellipse((365, 190, 385, 210), fill="#555555")
        d.ellipse((415, 190, 435, 210), fill="#555555")
        result.append(img)
    return result


def preview(layout_id, design, width=480):
    layout = LAYOUTS[layout_id]
    photos = placeholder_photos(layout["shots"])
    if layout_id == "classic":
        img = ImageOps.fit(photos[0], layout["size"])
    else:
        theme = THEMES.get(design.get("theme"), THEMES["party"])
        img = RENDERERS[layout_id](photos, design, theme, layout["size"])
    img.thumbnail((width, width))
    return img
