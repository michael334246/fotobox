@echo off
REM Fotobox starten: richtet beim ersten Start alles ein und oeffnet den Kiosk-Modus.
cd /d "%~dp0"

if not exist .venv (
    echo Richte Python-Umgebung ein ...
    py -3 -m venv .venv || python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

start "Fotobox Server" /min python app.py
timeout /t 3 /nobreak >nul

REM Vollbild-Kiosk mit Microsoft Edge (Beenden: Alt+F4)
start "" msedge --kiosk http://127.0.0.1:5050 --edge-kiosk-type=fullscreen --no-first-run
