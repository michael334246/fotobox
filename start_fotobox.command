#!/bin/bash
# Fotobox starten (Mac): richtet beim ersten Start alles ein und oeffnet den Vollbildmodus.
# Doppelklick im Finder genuegt. Beenden nur mit Admin-PIN ueber den Beenden-Knopf in der Fotobox.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 fehlt. Bitte von https://www.python.org/downloads/ installieren."
    read -r -p "Enter zum Schliessen ..."
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Richte Python-Umgebung ein ..."
    python3 -m venv .venv || exit 1
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt || exit 1
fi

# kiosk.py startet die Fotobox im Vollbild (Google Chrome) und oeffnet sie wieder,
# falls sie ohne Passwort geschlossen wird. Meldungen stehen in fotobox.log.
nohup .venv/bin/python kiosk.py >> fotobox.log 2>&1 &

if [ ! -d "/Applications/Google Chrome.app" ] && [ ! -d "/Applications/Microsoft Edge.app" ]; then
    echo "Google Chrome fehlt – die Fotobox oeffnet sich in Safari (Vollbild: Ctrl+Cmd+F)."
    echo "Der Schutz vor dem Schliessen funktioniert nur mit Google Chrome."
    sleep 4
    open "http://127.0.0.1:5050"
fi
echo "Die Fotobox laeuft. Dieses Fenster kann geschlossen werden."
