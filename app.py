"""Fotobox – einfache Fotobox-App mit Kamera, Windows-Druck und Cloud-Freigabe.

Start:  python app.py   (danach http://127.0.0.1:5050 im Browser / Kiosk-Modus öffnen)
"""
import base64
import datetime
import functools
import io
import os
import re
import secrets
import shutil
import tempfile
import threading
import uuid

import qrcode
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from core import camera, cloud, printer
from core import config as cfg

app = Flask(__name__)
app.secret_key = os.environ.get("FOTOBOX_SECRET") or secrets.token_hex(16)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

uploader = cloud.Uploader()
NAME_RE = re.compile(r"^[\w\-]+\.jpe?g$", re.IGNORECASE)


# --------------------------------------------------------------------------- Hilfsfunktionen
def photo_dir():
    path = cfg.load()["photo_dir"]
    os.makedirs(path, exist_ok=True)
    return path


def photo_path(name):
    if not NAME_RE.match(name):
        abort(404)
    path = os.path.join(photo_dir(), name)
    if not os.path.isfile(path):
        abort(404)
    return path


def new_photo_name():
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{stamp}_{uuid.uuid4().hex[:6]}.jpg"


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def find_storage(conf, storage_id):
    for s in conf["cloud"]["storages"]:
        if s.get("id") == storage_id:
            return s
    return None


def after_capture(name):
    """Automatischer Upload und ggf. automatischer Druck nach jeder Aufnahme."""
    conf = cfg.load()
    path = os.path.join(photo_dir(), name)
    auto = [s for s in conf["cloud"]["storages"] if s.get("auto_upload")]
    if auto:
        uploader.upload_async(auto, path, name)
    p = conf["printer"]
    if p["enabled"] and p["auto_print"]:
        def run():
            try:
                printer.print_image(path, p["name"], 1, p["fit_mode"])
            except Exception as exc:
                print(f"[Druck] Automatischer Druck fehlgeschlagen: {exc}")
        threading.Thread(target=run, daemon=True).start()


def admin_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        pin = cfg.load().get("admin_pin")
        if pin and session.get("admin") != pin:
            if request.path.startswith("/api/"):
                return error("Nicht angemeldet", 401)
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------------- Seiten
@app.route("/")
def index():
    return render_template("index.html", conf=cfg.load())


@app.route("/settings")
@admin_required
def settings():
    return render_template("settings.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    failed = False
    if request.method == "POST":
        if request.form.get("pin") == cfg.load().get("admin_pin"):
            session["admin"] = request.form["pin"]
            return redirect(url_for("settings"))
        failed = True
    return render_template("login.html", failed=failed)


@app.route("/photos/<name>")
def photo_file(name):
    photo_path(name)
    return send_from_directory(photo_dir(), name, max_age=3600)


# --------------------------------------------------------------------------- Fotobox-API
@app.get("/api/state")
def api_state():
    conf = cfg.load()
    return jsonify({
        "event_name": conf["event_name"],
        "countdown": conf["countdown"],
        "review_timeout": conf["review_timeout"],
        "camera": {k: conf["camera"][k] for k in ("mode", "webcam_device_id", "mirror_preview", "digicam_url")},
        "print_enabled": conf["printer"]["enabled"],
        "max_copies": conf["printer"]["max_copies"],
        "share_enabled": bool(find_storage(conf, conf["cloud"]["share_storage_id"])),
    })


@app.post("/api/photo")
def api_upload_photo():
    """Webcam-Aufnahme aus dem Browser entgegennehmen."""
    file = request.files.get("photo")
    if not file:
        return error("Kein Bild erhalten")
    name = new_photo_name()
    file.save(os.path.join(photo_dir(), name))
    after_capture(name)
    return jsonify({"ok": True, "name": name, "url": url_for("photo_file", name=name)})


@app.post("/api/capture")
def api_capture():
    """Spiegelreflex-/Systemkamera über digiCamControl oder gphoto2 auslösen."""
    conf = cfg.load()
    try:
        src = camera.capture(conf["camera"])
    except camera.CameraError as exc:
        return error(str(exc), 500)
    name = new_photo_name()
    if conf["camera"]["mode"] == "gphoto2":
        shutil.move(src, os.path.join(photo_dir(), name))
        shutil.rmtree(os.path.dirname(src), ignore_errors=True)
    else:
        shutil.copy2(src, os.path.join(photo_dir(), name))
    after_capture(name)
    return jsonify({"ok": True, "name": name, "url": url_for("photo_file", name=name)})


@app.post("/api/liveview/start")
def api_liveview_start():
    try:
        camera.start_liveview(cfg.load()["camera"])
    except camera.CameraError as exc:
        return error(str(exc), 500)
    return jsonify({"ok": True})


@app.get("/api/liveview.mjpg")
def api_liveview_gphoto():
    """Live-Ansicht der gphoto2-Kamera als MJPEG-Stream."""
    def stream():
        try:
            for frame in camera.gphoto.preview_frames():
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        except camera.CameraError as exc:
            print(f"[Kamera] {exc}")
    return Response(stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/photos")
def api_photos():
    names = sorted((n for n in os.listdir(photo_dir()) if NAME_RE.match(n)), reverse=True)[:60]
    return jsonify([{"name": n, "url": url_for("photo_file", name=n)} for n in names])


@app.post("/api/photos/<name>/print")
def api_print(name):
    conf = cfg.load()["printer"]
    if not conf["enabled"]:
        return error("Drucken ist deaktiviert")
    copies = min(max(int(request.json.get("copies", 1) if request.is_json else 1), 1), conf["max_copies"])
    try:
        printer.print_image(photo_path(name), conf["name"], copies, conf["fit_mode"])
    except Exception as exc:
        return error(str(exc), 500)
    return jsonify({"ok": True, "copies": copies})


@app.post("/api/photos/<name>/share")
def api_share(name):
    conf = cfg.load()
    storage = find_storage(conf, conf["cloud"]["share_storage_id"])
    if not storage:
        return error("Kein Cloudspeicher für die Freigabe ausgewählt")
    try:
        link = uploader.share(storage, photo_path(name), name)
    except Exception as exc:
        return error(f"Freigabe fehlgeschlagen: {exc}", 500)
    buf = io.BytesIO()
    qrcode.make(link, border=2).save(buf, format="PNG")
    qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return jsonify({"ok": True, "link": link, "qr": qr})


# --------------------------------------------------------------------------- Einstellungs-API
@app.get("/api/settings")
@admin_required
def api_get_settings():
    return jsonify({"config": cfg.load(), "storage_types": cloud.TYPES})


@app.post("/api/settings")
@admin_required
def api_save_settings():
    data = request.get_json(force=True)
    for s in data.get("cloud", {}).get("storages", []):
        s.setdefault("id", uuid.uuid4().hex[:8])
        if not s["id"]:
            s["id"] = uuid.uuid4().hex[:8]
    saved = cfg.save(data)
    if saved.get("admin_pin"):
        session["admin"] = saved["admin_pin"]
    return jsonify({"ok": True, "config": saved})


@app.get("/api/printers")
@admin_required
def api_printers():
    names, default = printer.list_printers()
    return jsonify({"printers": names, "default": default, "windows": printer.IS_WINDOWS,
                    "mac": printer.IS_MAC})


@app.post("/api/printers/connect")
@admin_required
def api_printer_connect():
    try:
        name, message = printer.connect_shared_printer(request.json.get("path", ""))
    except printer.PrinterError as exc:
        return error(str(exc))
    return jsonify({"ok": True, "name": name, "message": message})


@app.post("/api/printers/test")
@admin_required
def api_printer_test():
    from PIL import Image, ImageDraw
    conf = cfg.load()["printer"]
    path = os.path.join(tempfile.gettempdir(), "fotobox_testseite.jpg")
    img = Image.new("RGB", (1800, 1200), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((20, 20, 1780, 1180), outline="black", width=12)
    d.text((80, 80), "Fotobox Testdruck", fill="black")
    img.save(path)
    try:
        printer.print_image(path, conf["name"], 1, conf["fit_mode"])
    except Exception as exc:
        return error(str(exc), 500)
    return jsonify({"ok": True})


@app.post("/api/storages/test")
@admin_required
def api_storage_test():
    try:
        cloud.create(request.get_json(force=True)).test()
    except Exception as exc:
        return error(str(exc))
    return jsonify({"ok": True})


@app.get("/api/storages/status")
@admin_required
def api_storage_status():
    return jsonify({f"{k[0]}/{k[1]}": v for k, v in uploader.errors.items()})


@app.post("/api/dropbox/auth-url")
@admin_required
def api_dropbox_auth_url():
    return jsonify({"url": cloud.DropboxStorage.auth_url(request.json.get("app_key", ""))})


@app.post("/api/dropbox/exchange")
@admin_required
def api_dropbox_exchange():
    d = request.json
    try:
        token = cloud.DropboxStorage.exchange_code(d.get("app_key", ""), d.get("app_secret", ""), d.get("code", ""))
    except Exception as exc:
        return error(str(exc))
    return jsonify({"ok": True, "refresh_token": token})


if __name__ == "__main__":
    host = os.environ.get("FOTOBOX_HOST", "127.0.0.1")
    port = int(os.environ.get("FOTOBOX_PORT", "5050"))
    print(f"Fotobox läuft auf http://{host}:{port}  (Einstellungen: /settings)")
    app.run(host=host, port=port, threaded=True)
