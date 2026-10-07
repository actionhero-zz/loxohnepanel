#!/bin/bash
# LoxPanel (Favoriten-Fork) Docker-Steuerung.
# Nutzung: loxpanel-ctl.sh start|stop|restart|check|backup|restore <datei>
#   start   baut bei Bedarf das lokale Image (aus dem mitgelieferten
#           Quellcode unter config/app) und startet den Container
#   stop    stoppt den Container (merkt sich das -> check startet ihn NICHT neu)
#   restart stop + start  (baut dabei bei Aenderungen neu = manuelles Update)
#   check   startet den Container, falls er (unerwartet) nicht laeuft
#           (fuer Boot-daemon und 5-Minuten-Cron; ein bewusst gestopptes
#            Panel wird NICHT wieder gestartet)
#   backup  sichert die Konfiguration (Panels/Theme/Miniserver) als tar.gz
#   restore <datei>  spielt ein Backup zurueck (sichert vorher den Ist-Stand)
#
# Eigenstaendiger Fork: eigener Container-Name (loxpanelfav) und eigenes,
# LOKAL gebautes Image (kein Pull von ghcr.io/lenardo1/loxpanel) - laeuft
# unabhaengig neben einer evtl. installierten Original-LoxPanel-Version.
# REPLACELBPCONFIGDIR / REPLACELBPDATADIR werden beim Install durch echte Pfade ersetzt.

COMPOSE="REPLACELBPCONFIGDIR/docker-compose.yml"
STOPPED="REPLACELBPCONFIGDIR/loxpanelfav_stopped.cfg"
# Konfig-Daten liegen im gemounteten Volume (panels.json, theme.json,
# loxpanel.cfg) und gehoeren root (der Container schreibt als root). Backup/
# Restore laufen deshalb als root IM Container (sonst darf der Widget-Benutzer
# loxberry die root-Dateien nicht ueberschreiben -> "tar: Cannot open: File
# exists"). Sicherungen liegen in data/backups und ueberleben Plugin-Updates
# (pre-/postroot.sh sichern die Konfiguration ueber das Update hinweg).
DATADIR="REPLACELBPDATADIR"
CONFIGDATA="REPLACELBPDATADIR/config"
BACKUPDIR="REPLACELBPDATADIR/backups"
KEEP=20                 # so viele Backups behalten, aeltere werden entfernt
# Nicht ins Backup: heruntergeladene Fully-APKs (bis 80 MB, jederzeit neu ladbar)
# und die Ein-Generationen-Sicherung panels.json.bak - sonst waechst jedes Backup.
TAREX="--exclude=./adb/fully --exclude=./panels.json.bak --exclude=./diag.log*"

# Image aus der Compose-Datei lesen (Fallback fest: lokal gebautes Tag).
_img() {
	local i
	i=$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' "$COMPOSE" | head -1)
	[ -n "$i" ] && echo "$i" || echo "loxpanelfav:local"
}

# Einen sh-Befehl als root im Container ausfuehren. $DATADIR wird nach /data
# gemountet -> config=/data/config, backups=/data/backups.
_indocker() {
	sudo docker run --rm -v "$DATADIR":/data "$(_img)" sh -c "$1"
}

running() {
	[ -n "$(sudo docker ps --filter 'name=^/loxpanelfav$' --filter status=running -q 2>/dev/null)" ]
}

backup() {
	mkdir -p "$BACKUPDIR"     # als loxberry -> Verzeichnis bleibt loxberry-eigen (Loeschen moeglich)
	local ts f
	ts=$(date +%Y%m%d-%H%M%S)
	f="loxpanelfav-config-$ts.tar.gz"
	if _indocker "cd /data/config 2>/dev/null && tar -czf /data/backups/$f $TAREX . 2>/dev/null"; then
		echo "Backup erstellt: $f ($(du -h "$BACKUPDIR/$f" 2>/dev/null | cut -f1))"
	else
		echo "Backup fehlgeschlagen (Konfiguration vorhanden?)."; exit 1
	fi
	# aelteste ueber KEEP hinaus loeschen (Sicherungen vor Restore eingeschlossen)
	ls -1t "$BACKUPDIR"/loxpanelfav-config-*.tar.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
}

# Passwortschutz der Konfiguration entfernen (Passwort vergessen). Wirkt sofort.
resetpw() {
	if _indocker "python -c 'import json;p=\"/data/config/loxpanel.cfg\";d=json.load(open(p));d.pop(\"admin\",None);open(p,\"w\").write(json.dumps(d,indent=2,ensure_ascii=False))'"; then
		echo "Passwortschutz der Konfiguration entfernt."
	else
		echo "Zuruecksetzen fehlgeschlagen (Konfiguration vorhanden?)."; exit 1
	fi
}

restore() {
	local bn ts
	bn=$(basename "$1")     # nur Dateiname, keine Pfad-Tricks
	[ -f "$BACKUPDIR/$bn" ] || { echo "Backup nicht gefunden: $bn"; exit 1; }
	mkdir -p "$BACKUPDIR"
	ts=$(date +%Y%m%d-%H%M%S)
	# Ist-Stand vor dem Ueberschreiben sichern (Rueckweg offen halten)
	_indocker "cd /data/config 2>/dev/null && tar -czf /data/backups/loxpanelfav-config-$ts-vor-restore.tar.gz $TAREX . 2>/dev/null" \
		&& echo "Aktuellen Stand gesichert (loxpanelfav-config-$ts-vor-restore.tar.gz)."
	echo "Spiele $bn ein..."
	# config leeren und Backup als root einspielen (ueberschreibt root-Dateien)
	# adb/ (Schluessel + Fully-Cache) bleibt stehen: der Schluessel kommt aus dem
	# Backup zurueck, die APK muss nicht erneut geladen werden.
	if _indocker "mkdir -p /data/config && cd /data/config && find . -mindepth 1 -maxdepth 1 ! -name adb -exec rm -rf {} + && tar -xzf /data/backups/$bn -C /data/config"; then
		echo "Konfiguration wiederhergestellt."
	else
		echo "Wiederherstellung fehlgeschlagen."; exit 1
	fi
	# Container neu starten, damit die App die Panels frisch einliest (ohne Neu-Build)
	sudo docker restart loxpanelfav 2>&1 && echo "Panel neu gestartet."
}

start() {
	rm -f "$STOPPED"
	# Lokal bauen (nutzt den Build-Cache -> nur beim ersten Mal bzw. nach
	# Quellcode-Aenderungen dauert es laenger), danach starten. Kein 'pull':
	# es gibt kein Registry-Image, der Code kommt aus config/app/.
	# --provenance=false --sbom=false: spart die BuildKit-Standard-Attestationen
	# (Lieferketten-Metadaten) beim Export - bei einem rein lokal gebauten und
	# gestarteten Image (nie in eine Registry gepusht, nie von dort geprueft)
	# ungenutzt, kostet aber bei jedem Build ein, zwei Sekunden.
	sudo docker compose -f "$COMPOSE" build --provenance=false --sbom=false 2>&1
	sudo docker compose -f "$COMPOSE" up -d 2>&1
	# Vorgaengerversion des Images (nach dem Neubau namenlos, ~200 MB) entfernen -
	# nur verwaiste Images mit unserem Label, sonst sammeln sie sich je Update an.
	sudo docker image prune -f --filter "label=de.loxpanelfav.image=1" > /dev/null 2>&1 || true
	# Build-Cache: Schichten, die 30 Tage nicht mehr gebraucht wurden (alte
	# pip-Staende frueherer Updates) - waechst sonst mit jedem Update.
	sudo docker builder prune -f --filter "until=720h" > /dev/null 2>&1 || true
}

stop() {
	touch "$STOPPED"
	sudo docker compose -f "$COMPOSE" down 2>&1
}

case "$1" in
	start)   start ;;
	stop)    stop ;;
	restart) stop; start ;;
	check)
		[ -f "$STOPPED" ] && exit 0     # bewusst gestoppt -> nichts tun
		if ! running; then start
		# laeuft, antwortet aber nicht mehr (Healthcheck "unhealthy") -> neu starten
		elif [ "$(sudo docker inspect -f '{{.State.Health.Status}}' loxpanelfav 2>/dev/null)" = "unhealthy" ]; then
			echo "LoxPanel antwortet nicht (unhealthy) - Neustart."
			sudo docker restart loxpanelfav 2>&1
		fi
		;;
	backup)  backup ;;
	restore) restore "$2" ;;
	resetpw) resetpw ;;
	*) echo "Nutzung: $0 start|stop|restart|check|backup|restore <datei>|resetpw"; exit 1 ;;
esac
exit 0
