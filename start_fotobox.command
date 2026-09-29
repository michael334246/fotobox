#!/bin/bash
# Fotobox starten (Mac): richtet beim ersten Start alles ein und oeffnet den Vollbildmodus.
# Doppelklick im Finder genuegt. Beenden: dieses Terminalfenster schliessen.
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

URL="http://localhost:5000"
(
    sleep 3
    if [ -d "/Applications/Google Chrome.app" ]; then
        # Vollbild-Kiosk mit Google Chrome (Beenden: Cmd+Q)
        open -na "Google Chrome" --args --kiosk --app="$URL" --no-first-run
    else
        # Safari: Vollbild mit Ctrl+Cmd+F
        open "$URL"
    fi
) &

exec .venv/bin/python app.py
