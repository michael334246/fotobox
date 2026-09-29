# Fotobox

Einfache Fotobox-App für **Windows und Mac**: Kamera auslösen, Foto über einen (auch freigegebenen) Drucker drucken, automatisch in die Cloud hochladen und den Gästen per QR-Code aufs Handy geben.

| Funktion | Umsetzung |
|---|---|
| **Kamera** | Webcam/USB-Kamera direkt im Browser *oder* Spiegelreflex-/Systemkamera über [digiCamControl](https://digicamcontrol.com) (Windows) bzw. [gphoto2](http://www.gphoto.org) (Mac) |
| **Drucken** | Windows-Druckerverwaltung bzw. macOS-Drucksystem: lokale Drucker und **Windows-Druckerfreigaben** (`\\PC\Drucker`), direkt aus den Einstellungen verbindbar |
| **Cloudspeicher** | beliebig viele Speicher hinzufügen: Sync-Ordner (OneDrive, Google Drive, Dropbox-Client, SharePoint), Nextcloud/ownCloud, Dropbox, WebDAV (NAS) |
| **Teilen** | Nach der Aufnahme «Teilen» → Foto wird hochgeladen, ein öffentlicher Link erstellt und als QR-Code angezeigt |

## Installation (Windows)

1. [Python 3.10+](https://www.python.org/downloads/) installieren (Häkchen «Add Python to PATH» setzen).
2. Repository herunterladen (*Code → Download ZIP*) und entpacken, z.B. nach `C:\Fotobox`.
3. `start_fotobox.bat` doppelklicken. Beim ersten Start werden die Abhängigkeiten installiert, danach öffnet sich die Fotobox im Vollbild (Microsoft Edge Kiosk-Modus, beenden mit `Alt+F4`).
4. Beim ersten Start den Kamerazugriff im Browser erlauben.

Manuell: `pip install -r requirements.txt` und `python app.py`, dann <http://localhost:5000> öffnen.

## Installation (Mac)

1. [Python 3.10+](https://www.python.org/downloads/macos/) installieren (oder mit Homebrew: `brew install python`).
2. Repository herunterladen (*Code → Download ZIP*) und entpacken, z.B. nach `Programme/Fotobox` oder auf den Schreibtisch.
3. `start_fotobox.command` doppelklicken.
   - Beim allerersten Mal meldet macOS evtl. «nicht verifizierter Entwickler»: Rechtsklick auf die Datei → *Öffnen* → *Öffnen*.
   - Falls die Datei nicht startet: im Terminal einmalig `chmod +x start_fotobox.command` ausführen.
4. Beim ersten Start werden die Abhängigkeiten installiert. Danach öffnet sich die Fotobox im Vollbild in **Google Chrome** (Kiosk-Modus, beenden mit `Cmd+Q`). Ohne Chrome öffnet sich Safari – Vollbild dann mit `Ctrl+Cmd+F`.
5. Kamerazugriff erlauben (im Browser und ggf. unter *Systemeinstellungen → Datenschutz & Sicherheit → Kamera*).
6. Beenden: das Terminalfenster schliessen.

### Unterschiede auf dem Mac

| Thema | Mac |
|---|---|
| **Webcam** | FaceTime-Kamera oder USB-Webcam, genau wie unter Windows. |
| **Spiegelreflex / Systemkamera** | Über **gphoto2** statt digiCamControl: im Terminal `brew install gphoto2` ([Homebrew](https://brew.sh) nötig), Kamera per USB anschliessen, in den Einstellungen Kameratyp *«Spiegelreflex / Systemkamera – Mac (gphoto2)»* wählen. Live-Ansicht und Auslösen laufen über die App. An der Kamera JPEG (oder RAW+JPEG) einstellen. Unterstützte Kameras: [gphoto.org/proj/libgphoto2/support.php](http://www.gphoto.org/proj/libgphoto2/support.php). Die App beendet automatisch die macOS-Dienste, die angeschlossene Kameras sonst blockieren (z.B. beim Öffnen von «Fotos»). |
| **Drucker** | Alle Drucker aus *Systemeinstellungen → Drucker & Scanner* erscheinen in der Liste. Gedruckt wird über das macOS-Drucksystem (CUPS). |
| **Windows-Druckerfreigabe** | In den Einstellungen `\\EMPFANG-PC\Fotodrucker` (oder `smb://EMPFANG-PC/Fotodrucker`) eintragen und «Verbinden» klicken. Es öffnet sich der macOS-Dialog *Drucker hinzufügen*, die Adresse liegt schon in der Zwischenablage: Reiter *Windows* wählen (oder unter *IP* die Adresse einfügen), **Treiber des Druckers wählen**, hinzufügen. Danach in der Fotobox «Aktualisieren» und den Drucker auswählen. Der Treiber wird im Systemdialog gewählt, weil macOS ihn für Freigaben nicht automatisch findet. |
| **Papierformat** | Standard-Papierformat (z.B. 10×15 cm) in *Systemeinstellungen → Drucker & Scanner* bzw. im Druckdialog einer beliebigen App als Voreinstellung setzen. |
| **Cloudspeicher** | Alle Speicherarten funktionieren gleich. Als Sync-Ordner eignen sich z.B. `~/Library/Mobile Documents/com~apple~CloudDocs/Fotobox` (iCloud Drive), der OneDrive- oder Google-Drive-Ordner. |
| **Ruhezustand** | Für den Einsatz unter *Systemeinstellungen → Sperrbildschirm* den Bildschirmschoner/Ruhezustand ausschalten, damit die Fotobox nicht einschläft. |

## Bedienung

- **Foto machen:** grosser Knopf, Touchscreen, Leertaste oder Enter (USB-Buzzer, die eine Taste simulieren, funktionieren ebenfalls).
- Nach dem Countdown erscheint das Foto mit **Drucken** (Anzahl Kopien wählbar), **Teilen** (QR-Code) und **Neues Foto**.
- Nach der eingestellten Zeit ohne Bedienung springt die Fotobox automatisch zur Live-Ansicht zurück.
- 🖼️ oben rechts öffnet die Galerie (auch ältere Fotos drucken/teilen), ⚙️ die Einstellungen.
- Alle Fotos liegen zusätzlich lokal im Ordner `photos/`.

## Einstellungen (`/settings`)

Alle Einstellungen werden in `config.json` gespeichert. Mit einer **Admin-PIN** lässt sich die Einstellungsseite vor Gästen schützen.

### Kamera
- **Webcam:** Kamera auswählen («Kameras suchen»). Die Live-Ansicht kann gespiegelt werden; das gespeicherte Foto ist immer seitenrichtig.
- **Spiegelreflex – Mac (gphoto2):** siehe [Unterschiede auf dem Mac](#unterschiede-auf-dem-mac).
- **Spiegelreflex – Windows (digiCamControl):** digiCamControl installieren, Kamera per USB anschliessen, unter *Settings → Webserver* den Webserver aktivieren. In der Fotobox die Webserver-Adresse (Standard `http://localhost:5513`) und den **Session-Ordner** von digiCamControl eintragen, in dem die Bilder landen.

### Drucker
- Die Liste zeigt alle lokal installierten Drucker und verbundenen Druckerfreigaben.
- **Druckerfreigabe verbinden:** Pfad wie `\\EMPFANG-PC\Fotodrucker` eintragen und «Verbinden» klicken (entspricht *Windows → Drucker hinzufügen → Freigegebener Drucker*). Der Drucker muss auf dem anderen PC freigegeben sein (*Druckereigenschaften → Freigabe*).
- **Randlos** schneidet das Bild auf das Papierformat zu, **Ganzes Bild** lässt einen Rand.
- Papierformat und Qualität (z.B. 10×15 cm Fotopapier) im Windows-Treiber des Druckers als Standard einstellen.
- «Testseite drucken» prüft die Verbindung.

### Cloudspeicher
Unter «Neuen Cloudspeicher hinzufügen» Typ wählen, Felder ausfüllen, «Verbindung testen», speichern. Ist «Jedes Foto automatisch hochladen» aktiv, wird jedes Foto im Hintergrund hochgeladen.

| Typ | Einrichtung | Teilen-Link |
|---|---|---|
| **Sync-Ordner** | Ordner des OneDrive-/Google-Drive-/Dropbox-Clients angeben, z.B. `C:\Users\Fotobox\OneDrive\Fotobox`. Der Client lädt die Dateien hoch. | nur mit öffentlicher Basis-URL (z.B. Webserver); sonst nur Ablage |
| **Nextcloud / ownCloud** | Server-URL, Benutzer und **App-Passwort** (*Nextcloud → Persönliche Einstellungen → Sicherheit → Neues App-Passwort*), Zielordner | ✅ öffentlicher Link pro Foto |
| **Dropbox** | Auf <https://www.dropbox.com/developers/apps> eine App erstellen (*Scoped access*, *App folder*), Berechtigungen `files.content.write`, `files.content.read`, `sharing.write` aktivieren. App key + App secret eintragen, dann «1. Bei Dropbox anmelden» → Code kopieren → einfügen → «3. Verbinden» → speichern. | ✅ öffentlicher Link pro Foto |
| **WebDAV** | vollständige URL des Zielordners, Benutzer, Passwort (z.B. Synology/QNAP-NAS) | nur mit öffentlicher Basis-URL |

Unter **«Fotos teilen (QR-Code) über»** den Speicher wählen, der die Links für die Gäste erzeugt. Der Fotobox-PC braucht dafür Internet (z.B. Handy-Hotspot).

## Sicherheit

- Die App lauscht standardmässig nur auf `127.0.0.1` (nur dieser PC). Anderer Host/Port: Umgebungsvariablen `FOTOBOX_HOST` / `FOTOBOX_PORT`.
- Zugangsdaten der Cloudspeicher stehen im Klartext in `config.json` – den Fotobox-PC mit eigenem Windows-Benutzer betreiben und für Nextcloud/Dropbox eigene App-Passwörter bzw. einen App-Ordner verwenden.
- Teilen-Links sind öffentlich: Wer den Link kennt, sieht das jeweilige Foto.

## Aufbau

```
app.py              Webserver (Flask) und API
core/camera.py      Ansteuerung Spiegelreflex (digiCamControl / gphoto2)
core/printer.py     Drucken über Windows (pywin32) bzw. macOS (CUPS), Druckerfreigaben
core/cloud.py       Cloudspeicher, Upload und Freigabelinks
core/config.py      Einstellungen (config.json)
templates/, static/ Oberfläche (Fotobox + Einstellungen)
```
