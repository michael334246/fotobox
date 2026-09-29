# Fotobox

Einfache Fotobox-App für **Windows und Mac**: Kamera auslösen, Foto über einen (auch freigegebenen) Drucker drucken, automatisch in die Cloud hochladen und den Gästen per QR-Code aufs Handy geben.

| Funktion | Umsetzung |
|---|---|
| **Kamera** | Webcam/USB-Kamera direkt im Browser *oder* Spiegelreflex-/Systemkamera über [digiCamControl](https://digicamcontrol.com) (Windows) bzw. [gphoto2](http://www.gphoto.org) (Mac) |
| **Drucken** | Windows-Druckerverwaltung bzw. macOS-Drucksystem: lokale Drucker und **Windows-Druckerfreigaben** (`\\PC\Drucker`), direkt aus den Einstellungen verbindbar |
| **Cloudspeicher** | beliebig viele Speicher hinzufügen: Sync-Ordner (OneDrive, Google Drive, Dropbox-Client, SharePoint), Nextcloud/ownCloud, Dropbox, WebDAV (NAS) |
| **Layouts** | Gäste wählen vor dem Foto: *Klassisch*, *Mit Rahmen*, *Fotostreifen* (3 Fotos) oder *4er-Collage* – mit Anlassname, Datum und wählbarem Design |
| **Teilen** | Nach der Aufnahme «Teilen» → Foto wird hochgeladen, ein öffentlicher Link erstellt und als QR-Code angezeigt |

## Installation (Windows)

1. [Python 3.10+](https://www.python.org/downloads/) installieren (Häkchen «Add Python to PATH» setzen).
2. Repository herunterladen (*Code → Download ZIP*) und entpacken, z.B. nach `C:\Fotobox`.
3. `start_fotobox.bat` doppelklicken. Beim ersten Start werden die Abhängigkeiten installiert, danach öffnet sich die Fotobox im Vollbild (Microsoft Edge Kiosk-Modus, beenden mit `Alt+F4`).
4. Beim ersten Start den Kamerazugriff im Browser erlauben.

Manuell: `pip install -r requirements.txt` und `python app.py`, dann <http://127.0.0.1:5050> öffnen.

## Installation (Mac)

1. [Python 3.10+](https://www.python.org/downloads/macos/) installieren (oder mit Homebrew: `brew install python`).
2. Repository herunterladen (*Code → Download ZIP*) und entpacken, z.B. nach `Programme/Fotobox` oder auf den Schreibtisch.
3. `start_fotobox.command` doppelklicken.
   - **Meldung «kann nicht geöffnet werden» / «aus dem Internet geladen»:** Das ist der Schutz von macOS (Gatekeeper) für heruntergeladene Dateien. Meldung schliessen, dann *Systemeinstellungen → Datenschutz & Sicherheit* ganz nach unten scrollen und bei «start_fotobox.command wurde blockiert» auf **«Trotzdem öffnen»** klicken. Danach nochmals doppelklicken.
   - **Alternative über das Terminal:** `xattr -dr com.apple.quarantine ` eintippen (mit Leerzeichen am Schluss), den Fotobox-Ordner ins Terminalfenster ziehen, Enter. Damit entfernt macOS die Internet-Markierung für den ganzen Ordner.
   - Falls die Datei danach immer noch nicht startet: im Terminal einmalig `chmod +x ` eintippen, die Datei `start_fotobox.command` ins Fenster ziehen, Enter.
4. Beim ersten Start werden die Abhängigkeiten installiert. Danach öffnet sich die Fotobox im Vollbild in **Google Chrome** (Kiosk-Modus, beenden mit `Cmd+Q`). Ohne Chrome öffnet sich Safari – Vollbild dann mit `Ctrl+Cmd+F`.
5. Kamerazugriff erlauben (im Browser und ggf. unter *Systemeinstellungen → Datenschutz & Sicherheit → Kamera*).
6. Beenden: das Terminalfenster schliessen.

> Die Fotobox läuft auf Port **5050** (<http://127.0.0.1:5050>). Port 5000 ist auf dem Mac durch den AirPlay-Empfänger belegt und liefert «Zugriff auf localhost wurde verweigert». Ein anderer Port lässt sich mit der Umgebungsvariable `FOTOBOX_PORT` wählen.

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

- **Layout wählen:** unten die gewünschte Karte antippen (oder Pfeiltasten ← →).
- **Foto machen:** grosser Knopf «Los geht's!», Touchscreen, Leertaste oder Enter (USB-Buzzer, die eine Taste simulieren, funktionieren ebenfalls).
- Countdown mit lustigen Posen-Sprüchen; bei Fotostreifen und Collage werden automatisch mehrere Fotos nacheinander gemacht («Foto 2 von 4»).
- Danach erscheint das fertige Bild mit Konfetti und den Knöpfen **Drucken** (Anzahl Kopien wählbar), **Aufs Handy** (QR-Code) und **Nochmal!**.
- Nach der eingestellten Zeit ohne Bedienung springt die Fotobox automatisch zur Live-Ansicht zurück.
- 🖼️ oben rechts öffnet die Galerie (auch ältere Fotos drucken/teilen), ⚙️ die Einstellungen.
- Alle Fotos liegen zusätzlich lokal im Ordner `photos/`.

## Einstellungen (`/settings`)

Alle Einstellungen werden in `config.json` gespeichert. Mit einer **Admin-PIN** lässt sich die Einstellungsseite vor Gästen schützen.

### Design & Layouts

| Layout | Aufnahmen | Ergebnis (10×15 cm) |
|---|---|---|
| **Klassisch** | 1 | Originalfoto ohne Rahmen |
| **Mit Rahmen** | 1 | Foto mit Rand, darunter Anlassname und Datum |
| **Fotostreifen** | 3 | Zwei identische Streifen nebeneinander – in der Mitte durchschneiden, ergibt zwei klassische 5×15-cm-Fotostreifen |
| **4er-Collage** | 4 | 2×2 Fotos mit Anlassname und Datum |

- **Design:** *Party* (Violett/Pink mit Konfetti), *Bunt* (Sonnengelb), *Elegant* (Hochzeit, Creme/Gold) oder *Nacht* (Schwarz/Gold, z.B. Silvester).
- **Text auf dem Foto:** leer lassen = Name des Anlasses. Das Datum kann ausgeblendet werden.
- Welche Layouts die Gäste sehen und welches vorausgewählt ist, lässt sich einstellen. Die Vorschau zeigt das Design sofort.
- Die Einzelaufnahmen werden zusätzlich im Unterordner `photos/einzelbilder/` aufbewahrt.

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
core/layouts.py     Foto-Layouts und Designs (Rahmen, Collage, Fotostreifen)
core/config.py      Einstellungen (config.json)
templates/, static/ Oberfläche (Fotobox + Einstellungen)
static/fonts/       Schriften Pacifico und Baloo 2 (SIL Open Font License)
```
