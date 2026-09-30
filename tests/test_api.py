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
        self.client = fotobox.app.test_client()

    def tearDown(self):
        cfg.CONFIG_PATH = self._config_path
        self.tmp.cleanup()

    def test_all_urls_used_by_the_booth_exist(self):
        """Jede /api/…-Adresse aus static/app.js muss eine Route haben."""
        with open(os.path.join(BASE, "static", "app.js"), encoding="utf-8") as f:
            js = f.read()
        adapter = fotobox.app.url_map.bind("localhost")
        # Platzhalter in Template-Strings: als Pfadteil «x», sonst (z.B. angehängte Parameter) weglassen
        js = re.sub(r"\$\{[^}]*\}", "", re.sub(r"(?<=/)\$\{[^}]*\}", "x", js))
        for url in set(re.findall(r"[`\"'](/(?:api|shots|photos)/[^`\"'?]*)", js)):
            with self.subTest(url=url):
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


if __name__ == "__main__":
    unittest.main()
