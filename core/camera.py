"""Ansteuerung einer Spiegelreflex-/Systemkamera über digiCamControl.

Webcams werden direkt im Browser angesteuert (siehe static/app.js).
digiCamControl (https://digicamcontrol.com, Windows, kostenlos) unterstützt
die meisten Canon-, Nikon- und Sony-Kameras per USB. Dort muss unter
Einstellungen -> Webserver der Webserver aktiviert sein.
"""
import os
import time

import requests

IMAGE_EXT = (".jpg", ".jpeg")


class CameraError(Exception):
    pass


def _cmd(conf, command):
    base = conf["digicam_url"].rstrip("/")
    try:
        r = requests.get(f"{base}/", params={"CMD": command}, timeout=10)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise CameraError(
            f"digiCamControl nicht erreichbar ({base}). Läuft das Programm mit aktiviertem Webserver?"
        ) from exc


def start_liveview(conf):
    _cmd(conf, "LiveViewWnd_Show")


def capture(conf, timeout=25):
    """Löst die Kamera aus und gibt den Pfad des neuen Bildes zurück.

    digiCamControl speichert das Bild in seinem Sitzungsordner; dieser
    Ordner muss in den Fotobox-Einstellungen hinterlegt sein.
    """
    folder = conf.get("digicam_folder") or ""
    if not os.path.isdir(folder):
        raise CameraError("Der digiCamControl-Bildordner ist nicht gesetzt oder existiert nicht.")

    before = set(os.listdir(folder))
    _cmd(conf, "Capture")

    deadline = time.time() + timeout
    while time.time() < deadline:
        new = [f for f in os.listdir(folder) if f not in before and f.lower().endswith(IMAGE_EXT)]
        if new:
            path = os.path.join(folder, sorted(new)[-1])
            _wait_until_written(path)
            return path
        time.sleep(0.3)
    raise CameraError("Die Kamera hat kein Bild geliefert (Fokus gefunden? Speicherkarte/Akku?).")


def _wait_until_written(path, stable_for=0.5, max_wait=15):
    last = -1
    deadline = time.time() + max_wait
    while time.time() < deadline:
        size = os.path.getsize(path)
        if size == last and size > 0:
            return
        last = size
        time.sleep(stable_for)
