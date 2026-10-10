# Übergabe an die lokale Instanz (Stand 0.19.110, 2026-10-10)

Regeln und Arbeitsteilung stehen in `CLAUDE.md` – bitte zuerst lesen.

## Kurz
- Repo `actionhero-zz/loxohnepanel`, `main` = **0.19.110** (Commit `a71d0b8` + diese Übergabe).
- Ab jetzt: **lokal = alles außer adb/Android + alle Releases**, Cloud = nur adb/Android
  (pusht auf `claude/adb`, lokal mergen und releasen).
- Erste Schritte lokal:
  ```
  git fetch origin && git checkout main && git pull origin main
  ```

## Was bisher geschah (Changelog in README.md, Auszug)
- **Panel-Design (0.19.74–0.19.108):** Farben aus dem Theme, Loxone-Symbole, einheitliche
  Detailansichten und Pillen (Nebenaktionen als 44-px-Knöpfe im Kartenkopf), „Werte groß“
  auf Kacheln (globale Option + Kachel-Override), Zustand einzeilig auf Seiten mit Liste,
  Detailansichten ohne Scrollen im Raster, Handy-Format (Tabs unten), Querformat.
- **Bausteine:** Licht (Szenen ohne %, Zustand „An · Szene“), Heizung wie Rollladen,
  Jalousie, Bewässerung, Zentralbausteine einheitlich, Taster-Knopf, Intercom/Kamera
  (Bildausschnitt, Ränder, Klingel-Ende aus Loxone beendet auch offene Intercom).
- **Statusleiste:** Zahlen als Badge-Kreis am Symbol, Statustext je Baustein,
  Bausteine mit Meldungen zuerst, Nachtmodus nur Betriebsmodi.
- **Config:** Menü wie Panel-Tabs, Grid-Editor mit Konfiguration rechts, Monitoring im
  Miniserver-Bereich, Bausteine bei Loxone-Standard-Tabs ausblendbar, Design-Kritik
  umgesetzt.
- **Stabilität:** Diagnose-Log, Entlastung schwacher Panels/Shelly, nächtlicher
  Fully-Neustart, Geräte-Log.
- **Android (Cloud, 0.19.109/110):** Launcher 4.0 – Autostart nach 10 s mit Countdown
  (Tipp bricht ab), laufendes Fully nur nach vorn holen (Nutzungsstatistik, Recht per
  `appops`), Theme „Bunt“, targetSdk 24; Server überspringt Installation bei gleicher
  Version; Hinweis „Neue Launcher-Version im Update (3 → 4)“ unter „Einrichten per adb“.

## Offen
- [ ] Launcher 4.0 und Versions-Hinweis am echten Shelly testen (Einrichten → Fully
      verlassen → Countdown → Tipp bricht ab → Symbol holt Fully ohne Neuladen).
- [ ] In Fully dieselbe Panel-URL als Start-URL eintragen (nach Fully-Absturz startet
      Fully mit seiner eigenen Start-URL).
- [ ] README-Changelog: Einträge **0.19.105** und **0.19.91** stehen doppelt → aufräumen.
- [ ] Prüfen, ob LoxBerry die per `git archive` gebaute Plugin-ZIP annimmt.

## Schnittstellen zwischen beiden Teilen
- Beide ändern `webvisu.py` und `config.html` – Cloud nur in den in `CLAUDE.md`
  genannten adb-Funktionen. Bei Merge-Konflikten dort gilt der Stand von `claude/adb`.
- Versionsnummer und README-Changelog pflegt **nur** die lokale Instanz.
