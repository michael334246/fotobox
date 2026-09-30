"""Laden und Speichern der Einstellungen (config.json)."""
import copy
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULTS = {
    "event_name": "Fotobox",
    "countdown": 3,
    "review_timeout": 60,
    "admin_pin": "",
    "photo_dir": os.path.join(BASE_DIR, "photos"),
    "design": {
        "frame": "party",          # Rahmen, siehe core/layouts.py FRAMES ("none" = ohne Rahmen)
        "show_title": True,
        "frame_text": "",          # Titel auf dem Rahmen (leer = Name des Anlasses)
        "show_date": True,
        "guest_frames": False,     # Gäste dürfen den Rahmen selbst wählen
        "layouts": ["single", "strip", "grid"],
        "default_layout": "single",
        "logo": {"enabled": False, "position": "br", "size": 0.18},
        "custom_frames": [],       # eigene PNG-Rahmen (Dateien in uploads/)
        "edits": {},               # Änderungen aus dem Rahmen-Editor
    },
    "filters": {
        "enabled": True,           # Farb- und Gesichtsfilter für Gäste
    },
    "camera": {
        # "webcam": Kamera wird im Browser angesteuert (USB-Webcam, integrierte Kamera)
        # "dslr":   Spiegelreflex/Systemkamera über digiCamControl (Windows)
        "mode": "webcam",
        "webcam_device_id": "",
        "mirror_preview": True,
        "digicam_url": "http://localhost:5513",
        "digicam_folder": "",
    },
    "printer": {
        "enabled": True,
        "name": "",           # leer = Windows-Standarddrucker
        "max_copies": 3,
        "auto_print": False,
        "fit_mode": "fill",   # "fill" = randlos zuschneiden, "fit" = ganzes Bild mit Rand
    },
    "cloud": {
        "storages": [],       # Liste von Cloudspeichern, siehe core/cloud.py
        "share_storage_id": "",
    },
}

_lock = threading.Lock()


def _merge(defaults, data):
    result = copy.deepcopy(defaults)
    for key, value in (data or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load():
    with _lock:
        if not os.path.exists(CONFIG_PATH):
            return copy.deepcopy(DEFAULTS)
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    design = data.get("design") or {}
    if "theme" in design and "frame" not in design:  # Einstellungen vor der Rahmen-Galerie
        design["frame"] = {"bunt": "geburtstag", "elegant": "hochzeit", "nacht": "silvester"}.get(
            design["theme"], design["theme"])
    return _merge(DEFAULTS, data)


def save(data):
    data = _merge(DEFAULTS, data)
    with _lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
    return data
