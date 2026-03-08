# AGENTS.md – Maximo Asset Scan UI

## Ziel
Lokale Web-UI zum Erfassen und Einbuchen von Assets in Maximo.
Offline-fähig, läuft im Büro auf einem lokalen Rechner.
Kein Framework-Overhead – schlank und direkt.

---

## Stack
- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla HTML + JS (kein React, kein Vue)
- **Datenhaltung:** `queue.json` (lokal), `templates.json` (bereits vorhanden)
- **Maximo API:** POST `/maximo/oslc/os/mxapiasset`

---

## Projektstruktur

```
maximo/
  web/
    __init__.py
    app.py              ← FastAPI App + alle Routes
    templates/
      index.html        ← Haupt-UI
  model/
    queue.py            ← Queue lesen/schreiben
  oslc/
    post_asset.py       ← POST nach Maximo
cache/
  templates.json        ← bereits vorhanden (fetch_templates.py)
  queue.json            ← wird angelegt
```

---

## Aufgaben

### 1. `maximo/web/app.py`

FastAPI App mit diesen Routes:

| Method | Route | Beschreibung |
|--------|-------|-------------|
| GET | `/` | Liefert `index.html` |
| GET | `/api/templates` | Gibt `templates.json` zurück |
| POST | `/api/queue` | Fügt einen Eintrag zu `queue.json` hinzu |
| GET | `/api/queue` | Gibt aktuelle Queue zurück |
| DELETE | `/api/queue/{id}` | Entfernt Eintrag aus Queue |
| POST | `/api/upload` | Schickt alle Queue-Einträge nach Maximo |

Session (LtpaToken2) und Server wird aus webUI geladen – und an `session.py` übergeben.

---

### 2. `maximo/model/queue.py`

```python
# queue.json Eintrag
{
  "id": "uuid4",
  "itemnum": "CISCO.CATALYST.9200L",
  "description": "...",
  "siteid": "BWS00001",
  "orgid": "BTRBZ",
  "classstructureid": "2549",
  "location": "LOC-001",
  "serialnum": "SN-12345",
  "fixed_specs": { "BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L" },
  "user_specs": { "BAM.MACADRESSE": "F4:33:92:3A:79:80" },
  "status": "pending"  # pending | success | error
}
```

Funktionen:
- `load_queue() -> list`
- `save_queue(queue: list)`
- `add_to_queue(entry: dict) -> dict` (generiert id, setzt status=pending)
- `remove_from_queue(entry_id: str)`

---

### 3. `maximo/oslc/post_asset.py`

Baut den Maximo-Payload aus einem Queue-Eintrag und POSTet ihn.

**Payload-Struktur:**
```json
{
  "spi:itemnum": "...",
  "spi:siteid": "...",
  "spi:orgid": "...",
  "spi:location": "...",
  "spi:serialnum": "...",
  "spi:classstructureid": "...",
  "spi:assetspec": [
    { "spi:assetattrid": "BAM.TYPENBEZEICHNUNG", "spi:alnvalue": "..." },
    { "spi:assetattrid": "BAM.MACADRESSE", "spi:alnvalue": "..." }
  ]
}
```

fixed_specs + user_specs werden beide in `spi:assetspec` gemergt.

Funktion:
```python
def post_asset(server: str, session, entry: dict) -> dict:
    # returns {"success": True, "assetnum": "..."} or {"success": False, "error": "..."}
```

---

### 4. `maximo/web/templates/index.html`

Single-Page, kein Build-Step nötig.

**UI-Elemente:**

1. **Template-Dropdown** – durchsuchbar (type-ahead), zeigt `description (itemnum)`
2. **Dynamisches Formular** – generiert sich aus gewähltem Template:
   - `user_fields`: `serialnum`, `location` → Standard-Inputs
   - `user_specs`: je ein Input-Feld pro Spec-Attribut
   - `fixed_specs`: werden NICHT angezeigt (nur im Payload)
3. **„Zur Queue" Button** – validiert Pflichtfelder, POST an `/api/queue`
4. **Queue-Tabelle** – zeigt alle pending Einträge, mit Delete-Button
5. **„Alle einbuchen" Button** – POST an `/api/upload`, aktualisiert Status in Tabelle

**UX-Details:**
- Nach erfolgreichem Queue-Add: Formular reset, Fokus zurück auf Dropdown
- Barcode-Scanner funktioniert als Keyboard-Input (kein spezieller Handler nötig)
- Status-Farben: pending=grau, success=grün, error=rot

---

### 5. Startskript `run_web.py` (Projekt-Root)

```python
import uvicorn
uvicorn.run("maximo.web.app:app", host="127.0.0.1", port=8000, reload=False)
```

---

## Wichtige Hinweise

- Session/Token wird **einmalig** beim start der app abgefragt und geladen, nicht pro Request
- Kein Auth auf der Web-UI selbst (nur internes Büronetz)
- Queue persistiert auf Disk – App-Neustart verliert keine Daten
- `upload`-Route iteriert Queue, POSTet jedes pending-Item einzeln, updated Status
- Fehler beim Upload eines Items stoppen NICHT die restlichen Items

---

## Nicht umsetzen

- Kein Login/Auth auf der Web-UI
- Kein React/Vue/Svelte
- Keine Datenbank (nur JSON-Files)
- Keine automatische Sync-Loop (nur manuell per Button)
