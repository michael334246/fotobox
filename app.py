"""Fotobox – einfache Fotobox-App mit Kamera, Windows-Druck und Cloud-Freigabe.

Start:  python app.py   (danach http://127.0.0.1:5050 im Browser / Kiosk-Modus öffnen)
"""
import base64
import datetime
import functools
import io
import mimetypes
import os
import re
import secrets
import shutil
import tempfile
import threading
import uuid

import qrcode
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from core import camera, cloud, layouts, printer
from core import config as cfg
from PIL import Image, UnidentifiedImageError

# Windows kennt diese Dateitypen teils nicht – nötig für die Gesichtserkennung im Browser
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

app = Flask(__name__)
app.secret_key = os.environ.get("FOTOBOX_SECRET") or secrets.token_hex(16)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

uploader = cloud.Uploader()
EXIT_FLAG = os.path.join(cfg.BASE_DIR, ".fotobox-exit")
NAME_RE = re.compile(r"^[\w\-]+\.jpe?g$", re.IGNORECASE)
UPLOAD_DIR = os.path.join(cfg.BASE_DIR, "uploads")  # Logo und eigene Rahmen


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


def shots_dir():
    path = os.path.join(photo_dir(), "einzelbilder")
    os.makedirs(path, exist_ok=True)
    return path


def shot_path(name):
    if not NAME_RE.match(name or ""):
        abort(400)
    path = os.path.join(shots_dir(), name)
    if not os.path.isfile(path):
        abort(400)
    return path


def design_of(conf):
    design = layouts.normalize(conf["design"])
    design["frame_text"] = design.get("frame_text") or conf["event_name"]
    design["custom_frames"] = [dict(c, path=os.path.join(UPLOAD_DIR, c["file"])) for c in design["custom_frames"]]
    logo = os.path.join(UPLOAD_DIR, "logo.png")
    if os.path.exists(logo):
        design["logo_path"] = logo
        design["logo_mtime"] = os.path.getmtime(logo)  # neues Logo = neue Vorschau
    return design


def layout_ids(design):
    return {l["id"]: l for l in layouts.layout_list(design)}


def read_image(file):
    try:
        img = Image.open(file.stream)
        img.load()
        return img
    except (UnidentifiedImageError, OSError):
        abort(Response('{"ok": false, "error": "Das ist keine Bilddatei (PNG oder JPG)."}', 400,
                       mimetype="application/json"))


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


@app.route("/shots/<name>")
def shot_file(name):
    """Einzelaufnahme (für die Live-Vorschau bei Fotostreifen und Collage)."""
    shot_path(name)
    return send_from_directory(shots_dir(), name, max_age=3600)


# --------------------------------------------------------------------------- Fotobox-API
@app.get("/api/state")
def api_state():
    conf = cfg.load()
    design = design_of(conf)
    return jsonify({
        "event_name": conf["event_name"],
        "countdown": conf["countdown"],
        "review_timeout": conf["review_timeout"],
        "camera": {k: conf["camera"][k] for k in ("mode", "webcam_device_id", "mirror_preview", "digicam_url")},
        "print_enabled": conf["printer"]["enabled"],
        "max_copies": conf["printer"]["max_copies"],
        "share_enabled": bool(find_storage(conf, conf["cloud"]["share_storage_id"])),
        "layouts": [l for l in layouts.layout_list(design) if l["id"] in design["layouts"]],
        "default_layout": design["default_layout"],
        "frame": design["frame"],
        "guest_frames": design["guest_frames"],
        "filters_enabled": conf["filters"]["enabled"],
    })


@app.post("/api/shot")
def api_upload_shot():
    """Einzelaufnahme der Webcam aus dem Browser entgegennehmen."""
    file = request.files.get("photo")
    if not file:
        return error("Kein Bild erhalten")
    name = new_photo_name()
    file.save(os.path.join(shots_dir(), name))
    return jsonify({"ok": True, "shot": name})


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
        shutil.move(src, os.path.join(shots_dir(), name))
        shutil.rmtree(os.path.dirname(src), ignore_errors=True)
    else:
        shutil.copy2(src, os.path.join(shots_dir(), name))
    return jsonify({"ok": True, "shot": name})


@app.post("/api/compose")
def api_compose():
    """Einzelaufnahmen gemäss gewähltem Layout zum fertigen Foto zusammensetzen."""
    conf = cfg.load()
    data = request.get_json(force=True)
    layout_id = data.get("layout")
    all_layouts = layout_ids(design_of(conf))
    if layout_id not in all_layouts:
        return error("Unbekanntes Layout")
    paths = [shot_path(n) for n in data.get("shots", [])]
    if len(paths) != all_layouts[layout_id]["shots"]:
        return error("Falsche Anzahl Aufnahmen für dieses Layout")

    design = _guest_design(conf, data.get("frame"))

    name = new_photo_name()
    target = os.path.join(photo_dir(), name)
    try:
        image = layouts.compose(layout_id, paths, design)
    except Exception as exc:
        return error(f"Layout konnte nicht erstellt werden: {exc}", 500)
    if image is None:
        shutil.copy2(paths[0], target)
    else:
        image.save(target, quality=92, dpi=(300, 300))
    after_capture(name)
    return jsonify({"ok": True, "name": name, "url": url_for("photo_file", name=name)})


@app.get("/api/layouts/<layout_id>/preview.jpg")
def api_layout_preview(layout_id):
    """Vorschau mit Beispielbildern; Rahmen/Titel lassen sich per Parameter überschreiben."""
    if layout_id not in layout_ids(design_of(cfg.load())):
        abort(404)
    conf = cfg.load()
    design = design_of(conf)
    args = request.args
    if args.get("frame") in layouts.FRAMES or args.get("frame") == "none":
        design["frame"] = args["frame"]
    if "title" in args:
        design["frame_text"] = args["title"][:80] or conf["event_name"]
    for key in ("show_title", "show_date"):
        if key in args:
            design[key] = args[key] == "1"
    width = min(max(int(args.get("w", 480)), 120), 1200)
    resp = Response(layouts.preview_jpeg(layout_id, design, width), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "max-age=60"
    return resp


def _guest_design(conf, frame):
    """Gespeicherte Rahmen-Einstellungen, ggf. mit dem vom Gast gewählten Rahmen."""
    design = design_of(conf)
    if design["guest_frames"] and (frame in layouts.FRAMES or frame == "none"):
        design["frame"] = frame
    return design


@app.get("/api/layouts/<layout_id>/overlay")
def api_layout_overlay(layout_id):
    """Fotofelder der Live-Vorschau (der Rahmen selbst kommt als PNG von overlay.png)."""
    if layout_id not in layout_ids(design_of(cfg.load())):
        abort(404)
    return jsonify(layouts.overlay_info(layout_id, _guest_design(cfg.load(), request.args.get("frame"))))


@app.get("/api/layouts/<layout_id>/overlay.png")
def api_layout_overlay_png(layout_id):
    if layout_id not in layout_ids(design_of(cfg.load())):
        abort(404)
    png = layouts.overlay_png(layout_id, _guest_design(cfg.load(), request.args.get("frame")))
    resp = Response(png, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/exit")
def api_exit():
    """Fotobox beenden – nur mit Admin-PIN. kiosk.py sieht die Markierungsdatei und schliesst den Browser."""
    pin = cfg.load().get("admin_pin")
    if not pin:
        return error("Zuerst in den Einstellungen eine Admin-PIN festlegen – sie ist das Passwort zum Beenden.")
    if (request.get_json(silent=True) or {}).get("password") != pin:
        return error("Falsches Passwort", 403)
    with open(EXIT_FLAG, "w") as f:
        f.write("exit")
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


@app.get("/api/frames")
def api_frames():
    return jsonify(layouts.frame_list())


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


# --------------------------------------------------------------------------- Logo, eigene Rahmen, Editor
@app.get("/uploads/logo.png")
def logo_file():
    return send_from_directory(UPLOAD_DIR, "logo.png", max_age=0)


@app.post("/api/logo")
@admin_required
def api_logo_upload():
    img = read_image(request.files["file"]).convert("RGBA")
    img.thumbnail((1200, 1200))
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    img.save(os.path.join(UPLOAD_DIR, "logo.png"))
    return jsonify({"ok": True})


@app.delete("/api/logo")
@admin_required
def api_logo_delete():
    path = os.path.join(UPLOAD_DIR, "logo.png")
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.post("/api/custom-frames")
@admin_required
def api_custom_frame_upload():
    """Eigenen Rahmen (PNG mit durchsichtigen Fotofenstern) hochladen."""
    img = read_image(request.files["file"])
    if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
        return error("Der Rahmen braucht durchsichtige Fotofenster – bitte als PNG mit Transparenz speichern.")
    img = img.convert("RGBA")
    img.thumbnail((2400, 2400))
    holes = layouts.detect_holes(img)
    if not holes:
        return error("Im Rahmen wurde kein durchsichtiges Fotofenster gefunden.")
    if len(holes) > 8:
        return error(f"Zu viele durchsichtige Flächen gefunden ({len(holes)}); höchstens 8 Fotofenster.")
    frame_id = "custom-" + uuid.uuid4().hex[:6]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    img.save(os.path.join(UPLOAD_DIR, f"{frame_id}.png"))
    conf = cfg.load()
    name = (request.form.get("name") or "").strip()[:40] or "Eigener Rahmen"
    entry = {"id": frame_id, "name": name, "file": f"{frame_id}.png", "size": list(img.size), "holes": holes}
    conf["design"]["custom_frames"] = conf["design"].get("custom_frames", []) + [entry]
    conf["design"]["layouts"] = conf["design"].get("layouts", []) + [frame_id]
    saved = cfg.save(conf)
    return jsonify({"ok": True, "frame": entry, "config": saved})


@app.delete("/api/custom-frames/<frame_id>")
@admin_required
def api_custom_frame_delete(frame_id):
    conf = cfg.load()
    d = conf["design"]
    d["custom_frames"] = [c for c in d.get("custom_frames", []) if c["id"] != frame_id]
    d["layouts"] = [l for l in d.get("layouts", []) if l != frame_id]
    d.get("edits", {}).pop(frame_id, None)
    path = os.path.join(UPLOAD_DIR, f"{frame_id}.png")
    if re.fullmatch(r"custom-[0-9a-f]{6}", frame_id) and os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True, "config": cfg.save(conf)})


def _draft_design(data):
    """Gespeicherte Einstellungen, überlagert mit den noch nicht gespeicherten aus dem Editor."""
    conf = cfg.load()
    design = design_of(conf)
    for key in ("frame", "show_title", "show_date", "edits", "logo"):
        if key in data:
            design[key] = data[key]
    if "frame_text" in data:
        design["frame_text"] = data["frame_text"] or conf["event_name"]
    return design


@app.post("/api/editor/preview.jpg")
@admin_required
def api_editor_preview():
    data = request.get_json(force=True)
    design, layout_id = _draft_design(data), data.get("layout", "single")
    if layout_id not in layout_ids(design):
        abort(404)
    width = min(max(int(data.get("w", 520)), 120), 1200)
    if data.get("background"):  # ohne Titel/Logo/Sticker, Fotostreifen nur ein Streifen
        return Response(layouts.editor_background(layout_id, design, width), mimetype="image/jpeg")
    return Response(layouts.preview_jpeg(layout_id, design, width), mimetype="image/jpeg")


@app.post("/api/editor/info")
@admin_required
def api_editor_info():
    """Startwerte für den Editor: Farben/Schrift des Rahmens und Positionen der Elemente."""
    data = request.get_json(force=True)
    design, layout_id = _draft_design(data), data.get("layout", "single")
    key = layouts._edit_key(layout_id, design)
    pos = layouts.positions(layout_id, design) or layouts.default_positions(layout_id, design)
    custom = layouts._custom(design, layout_id)
    size = custom["size"] if custom else ([600, 1800] if layout_id == "strip" else [1800, 1200])
    return jsonify({"key": key, "style": layouts.frame_style(key if custom else design["frame"], design),
                    "positions": pos, "cell": size, "custom": bool(custom)})


@app.get("/api/stickers/<kind>.png")
def api_sticker(kind):
    if kind not in layouts.STICKERS:
        abort(404)
    return Response(layouts.sticker_png(kind), mimetype="image/png")


# --------------------------------------------------------------------------- Einstellungs-API
@app.get("/api/settings")
@admin_required
def api_get_settings():
    conf = cfg.load()
    conf["design"] = layouts.normalize(conf["design"])
    return jsonify({
        "config": conf,
        "storage_types": cloud.TYPES,
        "frames": layouts.frame_list(),
        "layouts": [[l["id"], l["label"]] for l in layouts.layout_list(conf["design"])],
        "stickers": [[k, v[0]] for k, v in layouts.STICKERS.items()],
        "logo": bool(design_of(conf).get("logo_path")),
    })


@app.post("/api/settings")
@admin_required
def api_save_settings():
    data = request.get_json(force=True)
    data["design"] = layouts.normalize(data.get("design"))
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
