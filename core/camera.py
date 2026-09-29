"""Ansteuerung einer Spiegelreflex-/Systemkamera.

Webcams werden direkt im Browser angesteuert (siehe static/app.js).

Windows: digiCamControl (https://digicamcontrol.com, kostenlos) unterstützt
die meisten Canon-, Nikon- und Sony-Kameras per USB. Dort muss unter
Einstellungen -> Webserver der Webserver aktiviert sein.

Mac/Linux: gphoto2 (http://www.gphoto.org, Mac: `brew install gphoto2`).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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


def capture(conf):
    """Löst die Kamera aus und gibt den Pfad des neuen Bildes zurück."""
    if conf.get("mode") == "gphoto2":
        return gphoto.capture()
    return capture_digicam(conf)


def capture_digicam(conf, timeout=25):
    """Auslösen über digiCamControl.

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


# --------------------------------------------------------------------------- gphoto2 (Mac/Linux)
class GPhoto:
    """Live-Ansicht und Auslösen über das Kommandozeilenprogramm gphoto2.

    Die Kamera kann immer nur von einem gphoto2-Prozess benutzt werden. Die
    Live-Ansicht wird deshalb vor dem Auslösen beendet und danach vom Browser
    neu angefordert.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._preview = None

    @staticmethod
    def _binary():
        path = shutil.which("gphoto2")
        if not path:
            raise CameraError("gphoto2 ist nicht installiert (Mac: «brew install gphoto2»).")
        return path

    @staticmethod
    def _release_macos_camera_daemon():
        # macOS belegt angeschlossene Kameras mit eigenen Diensten (Fotos, Digitale Bilder).
        if sys.platform == "darwin":
            for proc in ("PTPCamera", "mscamerad-xpc"):
                subprocess.run(["killall", proc], capture_output=True)

    def stop_preview(self):
        proc, self._preview = self._preview, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def preview_frames(self):
        """Liefert fortlaufend JPEG-Einzelbilder der Live-Ansicht."""
        with self._lock:
            self.stop_preview()
            self._release_macos_camera_daemon()
            proc = subprocess.Popen([self._binary(), "--stdout", "--capture-movie"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._preview = proc
        buf = b""
        try:
            while proc.poll() is None:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2)
                    if start < 0 or end < 0:
                        break
                    yield buf[start:end + 2]
                    buf = buf[end + 2:]
        finally:
            if self._preview is proc:
                self.stop_preview()

    def capture(self, timeout=30):
        with self._lock:
            self.stop_preview()
            self._release_macos_camera_daemon()
            target = os.path.join(tempfile.mkdtemp(prefix="fotobox_"), "bild.%C")
            try:
                subprocess.run(
                    [self._binary(), "--capture-image-and-download", "--force-overwrite",
                     "--filename", target],
                    capture_output=True, text=True, timeout=timeout, check=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise CameraError("Die Kamera hat nicht rechtzeitig ausgelöst.") from exc
            except subprocess.CalledProcessError as exc:
                msg = (exc.stderr or exc.stdout or "").strip().splitlines()
                raise CameraError("gphoto2: " + (msg[-1] if msg else "Auslösen fehlgeschlagen")) from exc
            folder = os.path.dirname(target)
            images = [f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT)]
            if not images:
                raise CameraError("Keine JPEG-Datei erhalten. Bitte an der Kamera JPEG (oder RAW+JPEG) einstellen.")
            return os.path.join(folder, images[0])


gphoto = GPhoto()
