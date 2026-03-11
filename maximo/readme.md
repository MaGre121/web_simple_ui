# Konfiguration

Die Laufzeit-Konfiguration kommt nicht mehr aus einer `.env`-Datei.

- `SERVER` wird in der Web-UI eingetragen und als nicht-geheime Einstellung im lokalen App-Ordner gespeichert.
- `LtpaToken2` wird in der Web-UI eingetragen, nur zur Laufzeit an das Backend uebergeben und nicht auf Disk gespeichert.
- Den Cookie findest du in der Browser-Entwicklerkonsole unter `Application` oder `Storage` bei den Cookies.

Fuer den normalen Web-UI-Betrieb:

1. `python run_web.py` starten
2. `http://127.0.0.1:8000` oeffnen
3. `SERVER` und `LtpaToken2` eintragen
4. `Hole Daten` ausfuehren
