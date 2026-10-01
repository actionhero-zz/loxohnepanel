# LoxPanel — Web-Touch-Visu fuer Loxone (Server + Frontend)
FROM python:3.12-slim

WORKDIR /app

# Abhaengigkeiten (loxone-api zieht aiohttp mit; cryptography fuer die
# Audioserver-Anmeldung). Auf 32-bit-ARM (linux/arm/v7) gibt es kein fertiges
# cffi-Paket -> Compiler + libffi/libc nur zum Bauen installieren und danach
# wieder entfernen, damit das Image schlank bleibt (amd64/arm64 nutzen Wheels).
COPY requirements.txt .
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends gcc libc6-dev libffi-dev; \
    pip install --no-cache-dir -r requirements.txt; \
    apt-get purge -y --auto-remove gcc libc6-dev libffi-dev; \
    rm -rf /var/lib/apt/lists/*

# adb: richtet Android-Panels (Shelly Wall Display) per Klick ein - installiert
# den LoxPanel-Launcher und traegt die Server-Adresse ein (api_panel_launcher).
# Eigener, fehlertoleranter Schritt: fehlt das Paket einmal, baut das Image
# trotzdem (das Panel laeuft weiter, nur die Einrichtung meldet "adb fehlt").
RUN apt-get update \
    && (apt-get install -y --no-install-recommends adb || echo "WARN: adb nicht installierbar") \
    && rm -rf /var/lib/apt/lists/*

# App-Code + Standard-Frontend/Config (Beispiele/Defaults)
# (ein Schritt statt sechs; tools/ bleibt draussen, siehe .dockerignore)
COPY . .

# Laufzeit-Config (loxpanel.cfg, panels.json, theme.json) wird als Volume
# unter /app/config gemountet; Miniserver-Zugang kann auch per Env kommen.
ENV LOXPANEL_PORT=8099
EXPOSE 8099

CMD ["python", "bin/webvisu.py"]
