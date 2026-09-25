# Entwickler-Werkzeuge

Diagnose- und Testskripte aus der Entwicklung. Sie laufen **nicht** im
Container (das Dockerfile kopiert nur `bin/`), sondern bei Bedarf direkt:

    python3 config/app/tools/<skript>.py

Skripte mit Miniserver-Zugriff lesen `config/app/config/loxpanel.cfg` und
importieren die Laufzeitmodule aus `../bin` (z. B. `loxone_ws`, `adapters`).
Skripte gegen das laufende Panel sprechen `http://localhost:8099` an.
