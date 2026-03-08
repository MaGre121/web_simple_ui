# Maximo Asset Scan UI

Lokale Web-Oberflaeche zum Erfassen und Einbuchen von Assets in Maximo.
Die Anwendung speichert ihre Queue lokal als JSON-Datei und sendet Eintraege erst manuell per Upload an Maximo.

## Uebersicht

- Backend: FastAPI
- Frontend: Vanilla HTML und JavaScript
- Persistenz: `maximo/cache/queue.json`
- Templates: `maximo/cache/templates.json`
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

Die Web-Anwendung liest ihre Maximo-Konfiguration aus der Datei `maximo/.env`.

1. Beispiel kopieren:

```bash
cp maximo/.env.example maximo/.env
```

2. `maximo/.env` befuellen:

```env
SERVER=https://dein-maximo-server
MAXIMO_LTPA_TOKEN2=dein_ltpatoken2_cookie
```

Hinweise:

- `SERVER` ist die Basis-URL der Maximo-Instanz.
- `MAXIMO_LTPA_TOKEN2` ist der Cookie-Wert aus dem Browser.
- Den Cookie findest du in der Browser-Entwicklerkonsole unter `Application` oder `Storage` bei den Cookies.
- Der Wert muss ohne zusaetzliche Leerzeichen eingefuegt werden.

## Templates vorbereiten

Vor dem ersten Start der Web-UI muss `templates.json` erzeugt werden.

```bash
python -m maximo.main
```

Dadurch werden die benoetigten Cache-Dateien unter `maximo/cache/` angelegt, insbesondere:

- `maximo/cache/templates.json`
- `maximo/cache/queue.json` wird spaeter automatisch erzeugt

Wenn `templates.json` fehlt, liefert die Web-UI bei `/api/templates` einen Fehler.

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

- `Zur Queue` speichert den Eintrag lokal in `maximo/cache/queue.json`.
- Nach erfolgreichem Speichern wird das Formular zurueckgesetzt.
- Der Fokus springt wieder auf das Template-Feld, damit ein Barcode-Scanner direkt weiterarbeiten kann.

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

- `maximo/cache/templates.json`: importierte Template-Daten
- `maximo/cache/queue.json`: lokale Upload-Queue

Die Queue bleibt auch nach einem Neustart der Anwendung erhalten.

## Typischer Ablauf

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp maximo/.env.example maximo/.env
# maximo/.env befuellen
python -m maximo.main
python -m compileall maximo run_web.py
python run_web.py
```

## Fehlerbilder

### `ModuleNotFoundError: No module named 'fastapi'`

Die Python-Abhaengigkeiten wurden noch nicht installiert:

```bash
pip install -r requirements.txt
```

### `templates.json` fehlt

Die Template-Daten wurden noch nicht aus Maximo geladen:

```bash
python -m maximo.main
```

### Maximo-Upload liefert Fehler

Pruefen:

- Ist `SERVER` in `maximo/.env` korrekt?
- Ist `MAXIMO_LTPA_TOKEN2` noch gueltig?
- Ist das gewaehlte Template in Maximo noch passend?
- Sind `location`, `serialnum` und alle sichtbaren Spec-Felder befuellt?
