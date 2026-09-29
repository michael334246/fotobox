"""Drucken über die Windows-Druckerverwaltung (inkl. freigegebener Netzwerkdrucker).

Unter Windows wird pywin32 verwendet. Auf dem Mac (und Linux) wird das
Drucksystem CUPS (`lp`, `lpstat`) verwendet.
"""
import os
import subprocess
import sys
from urllib.parse import quote

from PIL import Image, ImageOps

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


class PrinterError(Exception):
    pass


def list_printers():
    """Gibt (Liste der Druckernamen, Standarddrucker) zurück.

    Enthält lokale Drucker und verbundene Druckerfreigaben (\\\\PC\\Drucker).
    """
    if IS_WINDOWS:
        import win32print

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        names = sorted({p[2] for p in win32print.EnumPrinters(flags)})
        try:
            default = win32print.GetDefaultPrinter()
        except Exception:
            default = ""
        return names, default

    try:
        out = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=5).stdout
        names = [line.strip() for line in out.splitlines() if line.strip()]
        out = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, timeout=5).stdout
        default = out.split(":", 1)[1].strip() if ":" in out else ""
        return names, default
    except (OSError, subprocess.SubprocessError):
        return [], ""


def smb_url(path):
    """\\\\PC\\Drucker  ->  smb://PC/Drucker"""
    path = path.strip()
    if path.lower().startswith("smb://"):
        return path
    return "smb://" + quote(path.lstrip("\\").replace("\\", "/"))


def connect_shared_printer(path):
    """Verbindet eine Windows-Druckerfreigabe, z.B. \\\\EMPFANG-PC\\Fotodrucker.

    Gibt (Druckername oder "", Hinweistext) zurück.
    """
    path = (path or "").strip()
    if not (path.startswith("\\\\") or path.lower().startswith("smb://")):
        raise PrinterError("Bitte den Freigabepfad im Format \\\\COMPUTER\\Drucker angeben.")

    if IS_WINDOWS:
        import win32print

        if path.lower().startswith("smb://"):
            path = "\\\\" + path[6:].replace("/", "\\")
        try:
            win32print.AddPrinterConnection(path)
        except Exception as exc:  # pywintypes.error
            raise PrinterError(f"Verbindung zu {path} fehlgeschlagen: {exc}") from exc
        return path, f"{path} verbunden – bitte speichern"

    if IS_MAC:
        # macOS braucht für Freigaben den passenden Druckertreiber. Den wählt man am
        # zuverlässigsten im Systemdialog «Drucker hinzufügen» aus.
        url = smb_url(path)
        try:
            subprocess.run(["pbcopy"], input=url, text=True, timeout=5)
            if subprocess.run(["open", "-a", "AddPrinter"], capture_output=True).returncode != 0:
                subprocess.run(["open", "x-apple.systempreferences:com.apple.Print-Scanner-Settings.extension"])
        except (OSError, subprocess.SubprocessError) as exc:
            raise PrinterError(f"Dialog «Drucker hinzufügen» konnte nicht geöffnet werden: {exc}") from exc
        return "", (f"Im geöffneten Dialog Reiter «Windows» wählen oder unter «IP» die Adresse {url} "
                    "einfügen (bereits in der Zwischenablage), Treiber wählen, hinzufügen – "
                    "danach hier «Aktualisieren».")

    raise PrinterError("Druckerfreigaben bitte über die Druckereinstellungen des Systems verbinden.")


def print_image(path, printer_name="", copies=1, fit_mode="fill"):
    copies = max(1, int(copies))
    if IS_WINDOWS:
        _print_windows(path, printer_name, copies, fit_mode)
    else:
        _print_cups(path, printer_name, copies, fit_mode)


def _print_windows(path, printer_name, copies, fit_mode):
    import win32print
    import win32ui
    from PIL import ImageWin

    HORZRES, VERTRES = 8, 10
    name = printer_name or win32print.GetDefaultPrinter()

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    hdc = win32ui.CreateDC()
    try:
        hdc.CreatePrinterDC(name)
    except Exception as exc:
        raise PrinterError(f"Drucker '{name}' nicht erreichbar: {exc}") from exc

    try:
        pw, ph = hdc.GetDeviceCaps(HORZRES), hdc.GetDeviceCaps(VERTRES)
        # Bild an die Papierausrichtung anpassen
        if (img.width > img.height) != (pw > ph):
            img = img.rotate(90, expand=True)

        if fit_mode == "fill":
            img = ImageOps.fit(img, (pw, ph), Image.LANCZOS)
            box = (0, 0, pw, ph)
        else:
            scale = min(pw / img.width, ph / img.height)
            w, h = int(img.width * scale), int(img.height * scale)
            x, y = (pw - w) // 2, (ph - h) // 2
            box = (x, y, x + w, y + h)

        dib = ImageWin.Dib(img)
        for _ in range(copies):
            hdc.StartDoc(os.path.basename(path))
            hdc.StartPage()
            dib.draw(hdc.GetHandleOutput(), box)
            hdc.EndPage()
            hdc.EndDoc()
    finally:
        hdc.DeleteDC()


def _print_cups(path, printer_name, copies, fit_mode):
    cmd = ["lp", "-n", str(copies), "-o", "fill" if fit_mode == "fill" else "fit-to-page"]
    if printer_name:
        cmd += ["-d", printer_name]
    try:
        subprocess.run(cmd + [path], check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrinterError(f"Druck fehlgeschlagen: {exc}") from exc
