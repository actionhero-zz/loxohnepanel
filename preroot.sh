#!/bin/bash
# Laeuft als ROOT VOR der Installation.
# Args: <TEMPFOLDER> <NAME> <FOLDER> <VERSION> <BASEFOLDER>
ARGV3=$3   # Plugin-Ordnername
ARGV5=$5   # LoxBerry-Basisordner

# Docker installieren - aber NUR, wenn es wirklich noch fehlt, und dann HIER
# SELBST (nicht ueber LoxBerrys eigenen dpkg/apt-Mechanismus). Grund: dieses
# Plugin hat bewusst KEINE dpkg/apt-Datei mehr - waere dort die Docker-Paket-
# liste eingetragen, wuerde LoxBerry sie bei JEDER Installation/JEDEM Update
# bedingungslos neu herunterladen und reinstallieren, selbst wenn exakt diese
# Version schon laeuft (im Installer-Log sichtbar als "0 upgraded, 0 newly
# installed, 5 reinstalled" - ca. 90 MB und fast eine Minute reine Verschwendung
# bei jedem noch so kleinen Code-Update). Mit der Pruefung hier passiert das nur
# einmalig, beim allerersten Fehlen von Docker auf dem System.
if ! which docker > /dev/null 2>&1; then
	echo "<INFO> Docker fehlt - installiere es jetzt (einmalig, offizielles Docker-Repo)..."
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		| tee /etc/apt/sources.list.d/docker.list > /dev/null
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y --no-install-recommends \
		docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	# Frisch per systemd gestarteter Docker-Daemon braucht einen kurzen Moment,
	# bis der Socket da ist - kurz abwarten statt (unnoetig) auf einen Reboot
	# zu bestehen; unsere Skripte laufen ohnehin per sudo, keine Gruppen-
	# mitgliedschaft noetig, die einen Session-/Reboot-Neustart erfordern wuerde.
	for i in $(seq 1 15); do [ -S /var/run/docker.sock ] && break; sleep 1; done
	echo "<OK> Docker installiert."
else
	echo "<OK> Docker ist bereits installiert."
fi

# Laufenden Container vor dem (Neu-)Installieren stoppen (belegt sonst Port 8098).
CONFIGDIR="$ARGV5/config/plugins/$ARGV3"
if [ -f "$CONFIGDIR/docker-compose.yml" ]; then
	echo "<INFO> Stoppe laufendes LoxPanel (Favoriten-Fork)..."
	sudo docker compose -f "$CONFIGDIR/docker-compose.yml" down 2>/dev/null
fi
sudo docker rm -f loxpanelfav > /dev/null 2>&1

# Panel-Konfiguration (panels.json/theme.json/loxpanel.cfg) VOR dem Update
# sichern – als root, damit die root-eigenen Volume-Dateien lesbar sind.
# LoxBerry entfernt gleich danach den Datenordner; postroot.sh spielt die
# Konfiguration nach der Installation wieder zurueck.
LPBK="/tmp/loxpanelfav-upgrade-backup"
CFGDATA="$ARGV5/data/plugins/$ARGV3/config"
if [ -d "$CFGDATA" ] && [ -n "$(ls -A "$CFGDATA" 2>/dev/null)" ]; then
	rm -rf "$LPBK"; mkdir -p "$LPBK"
	if cp -a "$CFGDATA/." "$LPBK/" 2>/dev/null; then
		echo "<INFO> Panel-Konfiguration gesichert (Update-sicher)."
	fi
fi

# Versionsstempel fuer die Konfiguration (Version · Commit · Installiert):
# Das GitHub-ZIP traegt die Commit-Kennung als Archiv-Kommentar. Das Skript
# liegt im entpackten Ordner (uploads/<ID>/<repo-branch>/), das ZIP daneben
# (uploads/<ID>.zip). Fehlt etwas (anderes ZIP, kein unzip), bleibt der Commit leer.
SRC="$(cd "$(dirname "$0")" && pwd)"
COMMIT=""
for Z in "$(dirname "$SRC").zip" "$SRC.zip"; do
	[ -f "$Z" ] && COMMIT=$(unzip -z "$Z" 2>/dev/null | grep -oE '^[0-9a-f]{40}$' | head -1) && [ -n "$COMMIT" ] && break
done
if [ -d "$SRC/config/app/bin" ]; then
	printf '{"commit": "%s", "built": "%s"}\n' "$COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$SRC/config/app/bin/version.json"
	echo "<INFO> Versionsstempel: ${COMMIT:0:7} $(date '+%d.%m.%Y %H:%M')"
fi

# Besitzrechte der Daten-/Config-Ordner auf loxberry setzen.
chown -R loxberry:loxberry "$ARGV5/data/plugins/$ARGV3/" 2>/dev/null
chown -R loxberry:loxberry "$ARGV5/config/plugins/$ARGV3/" 2>/dev/null

exit 0
