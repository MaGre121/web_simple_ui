# Maximo Asset Scan UI

Lokale Web-Oberflaeche zum Erfassen und Einbuchen von Assets in Maximo.
Die Anwendung speichert ihre Queue lokal als JSON-Datei und sendet Eintraege erst manuell per Upload an Maximo.

## Uebersicht

- Backend: FastAPI
- Frontend: Vanilla HTML und JavaScript
- Persistenz: lokaler App-Ordner, z. B. `%LOCALAPPDATA%\MaximoAssetScanUI\cache\queue.json`
- Templates: lokaler App-Ordner, z. B. `%LOCALAPPDATA%\MaximoAssetScanUI\cache\templates.json`
- Startskript: `run_web.py`

## Voraussetzungen

- Eine aktuelle Python-3-Installation
- Zugriff auf die Maximo-Instanz
- Ein gueltiger `LtpaToken2`-Cookie aus dem Browser

## Installation

1. Virtuelle Umgebung anlegen:

```bash
python -m venv .venv
```

2. Umgebung aktivieren:

```bash
source .venv/bin/activate
```

3. Abhaengigkeiten installieren:

```bash
pip install -r requirements.txt
```

## Konfiguration

Die Web-Anwendung erwartet `SERVER` und `LtpaToken2` direkt im UI.

Nach dem Start gilt:

- `SERVER` ist die Basis-URL der Maximo-Instanz und wird lokal in `config.json` im App-Ordner gespeichert.
- `LtpaToken2` wird nur zur Laufzeit an das Backend uebergeben und nicht auf Disk geschrieben.
- Den Cookie findest du in der Browser-Entwicklerkonsole unter `Application` oder `Storage` bei den Cookies.
- Der Wert muss ohne zusaetzliche Leerzeichen eingefuegt werden.
- Fuer lokale Tests kann der App-Ordner ueber `MAXIMO_APP_DATA_DIR` umgebogen werden.

## Templates vorbereiten

Vor der ersten Benutzung muessen die Cache-Dateien einmal geladen werden.

1. Web-UI starten.
2. `SERVER` und `LtpaToken2` eintragen.
3. `Hole Daten` ausfuehren.

Dadurch werden die benoetigten Cache-Dateien im lokalen App-Ordner angelegt, insbesondere:

- `cache/templates.json`
- `cache/projects.json`
- `cache/users.json`
- `cache/locations_raw.json`
- `cache/locations_tree.json`
- `cache/queue.json` wird spaeter automatisch erzeugt

Optional bleibt `python -m maximo.main` als CLI-Refresh nutzbar, wenn `SERVER` und `MAXIMO_LTPA_TOKEN2` bereits als Prozess-Umgebungsvariablen gesetzt wurden.

## Kompilieren / Syntax pruefen

Python-Anwendungen werden nicht klassisch kompiliert. Fuer einen schnellen Syntax-Check kannst du Folgendes ausfuehren:

```bash
python -m compileall maximo run_web.py
```

Wenn der Befehl ohne Fehler durchlaeuft, sind die Python-Dateien syntaktisch gueltig.

## Anwendung starten

Die Web-UI startet lokal auf `127.0.0.1:8000`.

```bash
python run_web.py
```

Danach im Browser oeffnen:

```text
http://127.0.0.1:8000
```

## Windows EXE Build

Fuer einen Windows-Testbuild ist jetzt eine PyInstaller-Konfiguration vorhanden:

- `MaximoAssetScanUI.spec`
- `build_windows_exe.bat`
- `requirements-build.txt`

Build auf einem Windows-Rechner:

```bat
build_windows_exe.bat
```

Danach liegt die Datei hier:

```text
dist\MaximoAssetScanUI.exe
```

Hinweise:

- Der Build muss auf Windows ausgefuehrt werden, wenn du eine native Windows-`.exe` willst.
- Die EXE nutzt weiterhin den lokalen App-Ordner fuer `config.json` und `cache\*.json`.
- `LtpaToken2` bleibt auch im EXE-Betrieb runtime-only und wird nicht auf Disk geschrieben.

## Bedienung

### 1. Template auswaehlen

- Im Feld `Template` Beschreibung oder `itemnum` eingeben.
- Die Vorschlagsliste zeigt Eintraege im Format `Beschreibung (ITEMNUM)`.
- Nach exakter Auswahl wird das Formular automatisch aufgebaut.

### 2. Asset-Daten erfassen

Je nach Template erscheinen:

- Standardfelder wie `serialnum` und `location`
- Dynamische Spec-Felder aus `user_specs`

`fixed_specs` werden nicht angezeigt, aber spaeter mit an Maximo gesendet.

### 3. Zur Queue hinzufuegen

- `Zur Queue` speichert den Eintrag lokal in `cache/queue.json` im App-Ordner.
- Nach erfolgreichem Speichern wird das Formular zurueckgesetzt.
- Der Fokus springt wieder auf `serialnum`, damit ein Barcode-Scanner direkt weiterarbeiten kann.

### 4. Queue verwalten

Die Queue-Tabelle zeigt alle bisher erfassten Eintraege inklusive Status:

- `pending`: noch nicht hochgeladen
- `success`: erfolgreich an Maximo gesendet
- `error`: Upload fehlgeschlagen

Eintraege koennen ueber `Delete` aus der Queue entfernt werden.

### 5. Alle einbuchen

- `Alle einbuchen` verarbeitet alle Eintraege mit Status `pending`.
- Jeder Eintrag wird einzeln an Maximo gesendet.
- Fehler bei einem Eintrag stoppen die restlichen Eintraege nicht.
- Die Ergebnisse werden direkt in der Tabelle sichtbar.

## Datenablage

Die Anwendung arbeitet ohne Datenbank. Relevante Dateien:

- `config.json`: gespeicherter `SERVER`
- `cache/templates.json`: importierte Template-Daten
- `cache/projects.json`: importierte Projektdaten
- `cache/users.json`: importierte Benutzerdaten
- `cache/locations_raw.json` und `cache/locations_tree.json`: importierte Locations
- `cache/queue.json`: lokale Upload-Queue

Die Queue bleibt auch nach einem Neustart der Anwendung erhalten.
`LtpaToken2` wird nicht gespeichert.

## Typischer Ablauf

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m compileall maximo run_web.py
python run_web.py
```

Danach im Browser `http://127.0.0.1:8000` oeffnen, `SERVER` und `LtpaToken2` eingeben und `Hole Daten` ausfuehren.

## Fehlerbilder

### `ModuleNotFoundError: No module named 'fastapi'`

Die Python-Abhaengigkeiten wurden noch nicht installiert:

```bash
pip install -r requirements.txt
```

### `templates.json` fehlt

Die Template-Daten wurden noch nicht aus Maximo geladen:

Web-UI starten, `SERVER` und `LtpaToken2` eingeben und `Hole Daten` ausfuehren.

### Maximo-Upload liefert Fehler

Pruefen:

- Ist `SERVER` im UI korrekt?
- Wurde ein gueltiges `LtpaToken2` fuer die aktuelle Laufzeit gesetzt?
- Ist das gewaehlte Template in Maximo noch passend?
- Sind `location`, `serialnum` und alle sichtbaren Spec-Felder befuellt?
