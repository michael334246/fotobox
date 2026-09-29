"""Cloudspeicher: Hochladen von Fotos und Erzeugen von Freigabelinks.

Unterstützte Speicherarten:
  folder    – lokaler Sync-Ordner (OneDrive, Dropbox, Google Drive, SharePoint …)
  nextcloud – Nextcloud / ownCloud (WebDAV + öffentliche Freigabelinks)
  dropbox   – Dropbox-API (Upload + öffentliche Freigabelinks)
  webdav    – beliebiger WebDAV-Server (z.B. NAS), Links über eine Basis-URL
"""
import os
import shutil
import threading
import time
from urllib.parse import quote

import requests

TIMEOUT = 60

TYPES = {
    "folder": {
        "label": "Sync-Ordner (OneDrive, Google Drive, Dropbox-Client …)",
        "fields": [
            {"key": "path", "label": "Ordner auf diesem PC", "type": "text",
             "placeholder": r"C:\Users\Fotobox\OneDrive\Fotobox"},
            {"key": "public_base_url", "label": "Öffentliche Basis-URL (optional, für Teilen-Links)",
             "type": "text", "placeholder": "https://example.com/fotos/"},
        ],
    },
    "nextcloud": {
        "label": "Nextcloud / ownCloud",
        "fields": [
            {"key": "url", "label": "Server-URL", "type": "text", "placeholder": "https://cloud.example.ch"},
            {"key": "username", "label": "Benutzername", "type": "text"},
            {"key": "password", "label": "App-Passwort", "type": "password"},
            {"key": "remote_dir", "label": "Zielordner", "type": "text", "placeholder": "Fotobox/Anlass"},
        ],
    },
    "dropbox": {
        "label": "Dropbox",
        "fields": [
            {"key": "app_key", "label": "App key", "type": "text"},
            {"key": "app_secret", "label": "App secret", "type": "password"},
            {"key": "refresh_token", "label": "Refresh-Token (über «Dropbox verbinden»)", "type": "password"},
            {"key": "remote_dir", "label": "Zielordner", "type": "text", "placeholder": "/Fotobox"},
        ],
    },
    "webdav": {
        "label": "WebDAV (NAS, Webspace …)",
        "fields": [
            {"key": "url", "label": "WebDAV-Ordner-URL", "type": "text",
             "placeholder": "https://nas.local/webdav/fotobox/"},
            {"key": "username", "label": "Benutzername", "type": "text"},
            {"key": "password", "label": "Passwort", "type": "password"},
            {"key": "public_base_url", "label": "Öffentliche Basis-URL (optional, für Teilen-Links)",
             "type": "text"},
        ],
    },
}


class StorageError(Exception):
    pass


def _join_url(base, name):
    return base.rstrip("/") + "/" + quote(name)


def _check(resp, what):
    if resp.status_code >= 400:
        raise StorageError(f"{what} fehlgeschlagen (HTTP {resp.status_code}): {resp.text[:200]}")
    return resp


# --------------------------------------------------------------------------- Sync-Ordner
class FolderStorage:
    def __init__(self, conf):
        self.path = conf.get("path", "")
        self.base_url = conf.get("public_base_url", "")

    def test(self):
        os.makedirs(self.path, exist_ok=True)
        probe = os.path.join(self.path, ".fotobox-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)

    def upload(self, local_path, name):
        os.makedirs(self.path, exist_ok=True)
        shutil.copy2(local_path, os.path.join(self.path, name))

    def share_link(self, name):
        if not self.base_url:
            raise StorageError("Für diesen Sync-Ordner ist keine öffentliche Basis-URL hinterlegt.")
        return _join_url(self.base_url, name)


# --------------------------------------------------------------------------- Nextcloud
class NextcloudStorage:
    def __init__(self, conf):
        self.url = conf.get("url", "").rstrip("/")
        self.user = conf.get("username", "")
        self.auth = (self.user, conf.get("password", ""))
        self.remote_dir = conf.get("remote_dir", "Fotobox").strip("/")

    def _dav(self, path=""):
        parts = [quote(self.user)] + [quote(p) for p in self.remote_dir.split("/") if p]
        if path:
            parts.append(quote(path))
        return f"{self.url}/remote.php/dav/files/" + "/".join(parts)

    def _ensure_dir(self):
        current = f"{self.url}/remote.php/dav/files/{quote(self.user)}"
        for part in [p for p in self.remote_dir.split("/") if p]:
            current += "/" + quote(part)
            r = requests.request("MKCOL", current, auth=self.auth, timeout=TIMEOUT)
            if r.status_code not in (201, 405):  # 405 = existiert bereits
                _check(r, "Ordner anlegen")

    def test(self):
        self._ensure_dir()

    def upload(self, local_path, name):
        self._ensure_dir()
        with open(local_path, "rb") as f:
            _check(requests.put(self._dav(name), data=f, auth=self.auth, timeout=TIMEOUT), "Upload")

    def share_link(self, name):
        r = requests.post(
            f"{self.url}/ocs/v2.php/apps/files_sharing/api/v1/shares",
            auth=self.auth,
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            data={"path": f"/{self.remote_dir}/{name}", "shareType": 3, "permissions": 1},
            timeout=TIMEOUT,
        )
        _check(r, "Freigabe erstellen")
        return r.json()["ocs"]["data"]["url"]


# --------------------------------------------------------------------------- Dropbox
class DropboxStorage:
    _tokens = {}  # refresh_token -> (access_token, gültig_bis)

    def __init__(self, conf):
        self.app_key = conf.get("app_key", "")
        self.app_secret = conf.get("app_secret", "")
        self.refresh_token = conf.get("refresh_token", "")
        self.remote_dir = "/" + conf.get("remote_dir", "/Fotobox").strip("/")

    def _token(self):
        cached = self._tokens.get(self.refresh_token)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        if not self.refresh_token:
            raise StorageError("Dropbox ist noch nicht verbunden (Refresh-Token fehlt).")
        r = requests.post(
            "https://api.dropboxapi.com/oauth2/token",
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            auth=(self.app_key, self.app_secret),
            timeout=TIMEOUT,
        )
        _check(r, "Dropbox-Anmeldung")
        data = r.json()
        self._tokens[self.refresh_token] = (data["access_token"], time.time() + data.get("expires_in", 3600))
        return data["access_token"]

    def _path(self, name):
        return f"{self.remote_dir.rstrip('/')}/{name}"

    def test(self):
        r = requests.post("https://api.dropboxapi.com/2/users/get_current_account",
                          headers={"Authorization": f"Bearer {self._token()}"}, timeout=TIMEOUT)
        _check(r, "Dropbox-Verbindung")

    def upload(self, local_path, name):
        import json
        with open(local_path, "rb") as f:
            r = requests.post(
                "https://content.dropboxapi.com/2/files/upload",
                headers={
                    "Authorization": f"Bearer {self._token()}",
                    "Content-Type": "application/octet-stream",
                    "Dropbox-API-Arg": json.dumps({"path": self._path(name), "mode": "overwrite"}),
                },
                data=f,
                timeout=TIMEOUT,
            )
        _check(r, "Dropbox-Upload")

    def share_link(self, name):
        headers = {"Authorization": f"Bearer {self._token()}"}
        r = requests.post("https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
                          headers=headers, json={"path": self._path(name)}, timeout=TIMEOUT)
        if r.status_code == 409 and "shared_link_already_exists" in r.text:
            r = requests.post("https://api.dropboxapi.com/2/sharing/list_shared_links",
                              headers=headers, json={"path": self._path(name), "direct_only": True},
                              timeout=TIMEOUT)
            _check(r, "Dropbox-Freigabe")
            return r.json()["links"][0]["url"]
        _check(r, "Dropbox-Freigabe")
        return r.json()["url"]

    @staticmethod
    def auth_url(app_key):
        return ("https://www.dropbox.com/oauth2/authorize?response_type=code"
                f"&token_access_type=offline&client_id={quote(app_key)}")

    @staticmethod
    def exchange_code(app_key, app_secret, code):
        r = requests.post("https://api.dropboxapi.com/oauth2/token",
                          data={"grant_type": "authorization_code", "code": code.strip()},
                          auth=(app_key, app_secret), timeout=TIMEOUT)
        _check(r, "Dropbox-Anmeldung")
        return r.json()["refresh_token"]


# --------------------------------------------------------------------------- WebDAV
class WebDavStorage:
    def __init__(self, conf):
        self.url = conf.get("url", "")
        self.auth = (conf.get("username", ""), conf.get("password", ""))
        self.base_url = conf.get("public_base_url", "")

    def test(self):
        r = requests.request("PROPFIND", self.url, auth=self.auth, headers={"Depth": "0"}, timeout=TIMEOUT)
        _check(r, "WebDAV-Verbindung")

    def upload(self, local_path, name):
        with open(local_path, "rb") as f:
            _check(requests.put(_join_url(self.url, name), data=f, auth=self.auth, timeout=TIMEOUT),
                   "WebDAV-Upload")

    def share_link(self, name):
        if not self.base_url:
            raise StorageError("Für diesen WebDAV-Speicher ist keine öffentliche Basis-URL hinterlegt.")
        return _join_url(self.base_url, name)


CLASSES = {
    "folder": FolderStorage,
    "nextcloud": NextcloudStorage,
    "dropbox": DropboxStorage,
    "webdav": WebDavStorage,
}


def create(storage_conf):
    cls = CLASSES.get(storage_conf.get("type"))
    if not cls:
        raise StorageError(f"Unbekannter Speichertyp: {storage_conf.get('type')}")
    return cls(storage_conf)


# --------------------------------------------------------------------------- Upload-Verwaltung
class Uploader:
    """Merkt sich erledigte Uploads/Links, damit nichts doppelt hochgeladen wird."""

    def __init__(self):
        self._done = {}    # (storage_id, name) -> True
        self._links = {}   # (storage_id, name) -> url
        self._locks = {}
        self._guard = threading.Lock()
        self.errors = {}   # (storage_id, name) -> Fehlermeldung

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def upload(self, storage_conf, local_path, name):
        key = (storage_conf["id"], name)
        with self._lock(key):
            if key not in self._done:
                create(storage_conf).upload(local_path, name)
                self._done[key] = True
                self.errors.pop(key, None)

    def share(self, storage_conf, local_path, name):
        key = (storage_conf["id"], name)
        self.upload(storage_conf, local_path, name)
        with self._lock(key):
            if key not in self._links:
                self._links[key] = create(storage_conf).share_link(name)
            return self._links[key]

    def upload_async(self, storages, local_path, name):
        def run(conf):
            try:
                self.upload(conf, local_path, name)
            except Exception as exc:  # Fehler nur protokollieren, Fotobox läuft weiter
                self.errors[(conf["id"], name)] = str(exc)
                print(f"[Cloud] Upload von {name} nach '{conf.get('name')}' fehlgeschlagen: {exc}")

        for conf in storages:
            threading.Thread(target=run, args=(conf,), daemon=True).start()
