# LoxPanel — Web-Touch-Visu fuer Loxone (Server + Frontend)
FROM python:3.12-slim
# Kennzeichnung: loxpanel-ctl.sh raeumt nach einem Neubau nur verwaiste Images
# MIT diesem Label weg - Images anderer Plugins bleiben unberuehrt.
LABEL de.loxpanelfav.image="1"

WORKDIR /app

# Abhaengigkeiten (loxone-api zieht aiohttp mit; cryptography fuer die
# Audioserver-Anmeldung). Hardware-unabhaengig in zwei Stufen:
#  1. ohne Compiler mit fertigen Paketen (Wheels) - klappt auf amd64/arm64 und
#     ueberall, wo es Wheels gibt; spart ~80 s und ~57 MB Download je Neubau.
#  2. nur wenn das scheitert (z.B. 32-bit-ARM ohne cffi-Wheel, exotische
#     Plattform): Compiler + libffi/libc installieren, bauen, wieder entfernen.
COPY requirements.txt .
RUN set -eux; \
    if pip install --no-cache-dir --prefer-binary -r requirements.txt; then \
        echo "Python-Pakete ohne Compiler installiert"; \
    else \
        echo "Fertige Pakete reichen hier nicht - baue mit Compiler"; \
        apt-get update; \
        apt-get install -y --no-install-recommends gcc libc6-dev libffi-dev; \
        pip install --no-cache-dir -r requirements.txt; \
        apt-get purge -y --auto-remove gcc libc6-dev libffi-dev; \
        rm -rf /var/lib/apt/lists/*; \
    fi

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
