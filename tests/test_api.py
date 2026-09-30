"""Rauchtest der Fotobox-API: spielt die Knöpfe der Oberfläche einmal durch.

Start:  python -m unittest discover tests
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest

from PIL import Image
from werkzeug.exceptions import MethodNotAllowed, NotFound

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import app as fotobox  # noqa: E402
from core import config as cfg  # noqa: E402


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), "orange").save(buf, format="JPEG")
    buf.seek(0)
    return buf


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._config_path = cfg.CONFIG_PATH
        cfg.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        cfg.save({
            "admin_pin": "4711",
            "photo_dir": os.path.join(self.tmp.name, "photos"),
            "printer": {"enabled": False},
            "cloud": {"storages": [{"id": "s1", "type": "folder", "name": "Test",
                                    "path": os.path.join(self.tmp.name, "cloud"),
                                    "public_base_url": "https://example.com/f/"}],
                      "share_storage_id": "s1"},
        })
        self._upload_dir = fotobox.UPLOAD_DIR
        fotobox.UPLOAD_DIR = os.path.join(self.tmp.name, "uploads")
        self.client = fotobox.app.test_client()

    def tearDown(self):
        cfg.CONFIG_PATH = self._config_path
        fotobox.UPLOAD_DIR = self._upload_dir
        self.tmp.cleanup()

    def login(self):
        with self.client.session_transaction() as session:
            session["admin"] = "4711"

    def test_all_urls_used_by_the_booth_exist(self):
        """Jede /api/…-Adresse aus den Skripten der Oberfläche muss eine Route haben."""
        js = ""
        for name in ("app.js", "filters.js", "settings.js", "editor.js"):
            with open(os.path.join(BASE, "static", name), encoding="utf-8") as f:
                js += f.read()
        adapter = fotobox.app.url_map.bind("localhost")
        # Platzhalter in Template-Strings: als Pfadteil «x», sonst (z.B. angehängte Parameter) weglassen
        js = re.sub(r"\$\{[^}]*\}", "", re.sub(r"(?<=/)\$\{[^}]*\}", "x", js))
        for url in set(re.findall(r"[`\"'](/(?:api|shots|photos|uploads|static)/[^`\"'?]*)", js)):
            with self.subTest(url=url):
                if url.startswith("/static/"):
                    self.assertTrue(os.path.exists(BASE + url), f"Datei fehlt: {url}")
                    continue
                try:
                    adapter.match(url, method="GET")
                except MethodNotAllowed:
                    pass  # Route existiert, nur mit anderer Methode
                except NotFound:
                    self.fail(f"Keine Route für {url}")

    def test_photo_flow(self):
        shot = self.client.post("/api/shot", data={"photo": (jpeg(), "a.jpg")}).get_json()["shot"]
        photo = self.client.post("/api/compose", json={"layout": "single", "shots": [shot]}).get_json()
        self.assertTrue(photo["ok"])
        name = photo["name"]

        self.assertIn(name, [p["name"] for p in self.client.get("/api/photos").get_json()])

        share = self.client.post(f"/api/photos/{name}/share").get_json()
        self.assertTrue(share["ok"], share)
        self.assertEqual(share["link"], f"https://example.com/f/{name}")
        self.assertTrue(share["qr"].startswith("data:image/png;base64,"))

        printed = self.client.post(f"/api/photos/{name}/print", json={"copies": 1})
        self.assertEqual(printed.get_json()["error"], "Drucken ist deaktiviert")

    def test_overlay_and_exit(self):
        info = self.client.get("/api/layouts/grid/overlay").get_json()
        self.assertEqual(len(info["holes"]), 4)
        self.assertEqual(self.client.get("/api/layouts/grid/overlay.png").status_code, 200)
        self.assertEqual(self.client.post("/api/exit", json={"password": "0000"}).status_code, 403)


    def test_logo_custom_frame_and_editor(self):
        self.login()
        # Logo
        r = self.client.post("/api/logo", data={"file": (jpeg(), "logo.jpg")})
        self.assertTrue(r.get_json()["ok"])
        with self.client.get("/uploads/logo.png") as logo:
            self.assertEqual(logo.status_code, 200)

        # Eigener Rahmen mit zwei durchsichtigen Fenstern
        png = Image.new("RGBA", (1800, 1200), (20, 60, 160, 255))
        png.paste((0, 0, 0, 0), (100, 100, 850, 1100))
        png.paste((0, 0, 0, 0), (950, 100, 1700, 1100))
        buf = io.BytesIO()
        png.save(buf, format="PNG")
        buf.seek(0)
        frame = self.client.post("/api/custom-frames", data={"file": (buf, "r.png"), "name": "Test"}).get_json()
        self.assertTrue(frame["ok"], frame)
        self.assertEqual(len(frame["frame"]["holes"]), 2)
        layout = frame["frame"]["id"]

        # JPG ohne Transparenz wird abgelehnt
        bad = self.client.post("/api/custom-frames", data={"file": (jpeg(), "r.jpg")}).get_json()
        self.assertFalse(bad["ok"])

        # Mit dem eigenen Rahmen fotografieren
        shots = [self.client.post("/api/shot", data={"photo": (jpeg(), "a.jpg")}).get_json()["shot"] for _ in range(2)]
        photo = self.client.post("/api/compose", json={"layout": layout, "shots": shots}).get_json()
        self.assertTrue(photo["ok"], photo)
        self.assertEqual(len(self.client.get(f"/api/layouts/{layout}/overlay").get_json()["holes"]), 2)

        # Editor: Entwurf mit Farbe, Sticker und Positionen
        edits = {"party": {"base": "#000000", "pos": {"single": {"title": [0.5, 0.9, 0.07], "date": [0.5, 0.95, 0.03],
                                                                 "stickers": [["herz", 0.2, 0.2, 0.1]]}}}}
        r = self.client.post("/api/editor/preview.jpg", json={"layout": "single", "frame": "party", "edits": edits})
        self.assertEqual(r.mimetype, "image/jpeg")
        info = self.client.post("/api/editor/info", json={"layout": "single", "frame": "party", "edits": edits}).get_json()
        self.assertEqual(info["positions"]["stickers"][0][0], "herz")
        self.assertEqual(self.client.get("/api/stickers/herz.png").mimetype, "image/png")

        # Rahmen wieder entfernen
        self.assertTrue(self.client.delete(f"/api/custom-frames/{layout}").get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
