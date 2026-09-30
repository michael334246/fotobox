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

REM Fotobox im Vollbild starten (ohne Konsolenfenster). Schliessen nur mit Admin-PIN
REM ueber den Beenden-Knopf in der Fotobox; Meldungen stehen in fotobox.log.
start "" .venv\Scripts\pythonw.exe kiosk.py
