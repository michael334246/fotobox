"""Startet die Fotobox im Vollbild (Kiosk-Modus) und hält sie offen.

Wird der Browser geschlossen (z.B. mit Alt+F4 oder Cmd+Q), öffnet kiosk.py ihn
sofort wieder. Beenden lässt sich die Fotobox nur über den Beenden-Knopf mit der
Admin-PIN: Die App legt dann die Datei .fotobox-exit an und beendet sich,
worauf kiosk.py auch den Browser schliesst.

Start:  python kiosk.py   (die Startskripte start_fotobox.bat/.command tun das)
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
EXIT_FLAG = os.path.join(BASE, ".fotobox-exit")
PORT = os.environ.get("FOTOBOX_PORT", "5050")
URL = f"http://127.0.0.1:{PORT}"


def find_browser():
    """Chrome oder Edge suchen (nur diese beherrschen den Kiosk-Modus zuverlässig)."""
    if os.environ.get("FOTOBOX_BROWSER"):
        return os.environ["FOTOBOX_BROWSER"]
    candidates = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates += [os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                               os.path.join(base, r"Google\Chrome\Application\chrome.exe")]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                       "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for path in candidates:
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def browser_command(path):
    # Eigenes Profil: startet einen eigenen Browser-Prozess, den kiosk.py überwachen kann,
    # und merkt sich die Kamera-Freigabe.
    profile = os.path.join(BASE, ".browser-profile")
    return [path, "--kiosk", URL, "--edge-kiosk-type=fullscreen", "--no-first-run",
            "--no-default-browser-check", "--disable-session-crashed-bubble", f"--user-data-dir={profile}"]


def wait_for_server(server, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline and server.poll() is None:
        try:
            urllib.request.urlopen(f"{URL}/api/state", timeout=2)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    if os.path.exists(EXIT_FLAG):
        os.remove(EXIT_FLAG)
    log = open(os.path.join(BASE, "fotobox.log"), "a", encoding="utf-8")
    server = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py")], cwd=BASE, stdout=log, stderr=log)
    browser = None
    try:
        if not wait_for_server(server):
            print("Die Fotobox konnte nicht gestartet werden – Details in fotobox.log.")
            return 1
        path = find_browser()
        if not path:
            print(f"Kein Chrome oder Edge gefunden. Bitte {URL} im Browser öffnen.")
            server.wait()
            return 0
        while not os.path.exists(EXIT_FLAG) and server.poll() is None:
            if browser is None or browser.poll() is not None:
                browser = subprocess.Popen(browser_command(path), stdout=log, stderr=log)
            time.sleep(1)
    finally:
        stop(browser)
        stop(server)
        if os.path.exists(EXIT_FLAG):
            os.remove(EXIT_FLAG)
        log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
