# LoxPanel Favoriten – LoxBerry-Plugin (Docker, eigenstaendiger Fork)

Betreibt den **Favoriten-Fork von LoxPanel** als eigenen Docker-Container auf
einem LoxBerry – bewusst als **eigenstaendiges Plugin neben einer evtl.
installierten Original-LoxPanel-Version**, ohne Kollision:

- eigene Plugin-Identitaet (`FOLDER=loxpanelfav`, eigener Autor-Schluessel)
- eigener Container-/Hostname (`loxpanelfav` statt `loxpanel`)
- eigener Host-Port (**8098** statt 8099)
- eigenes Image, **lokal aus dem mitgelieferten Quellcode gebaut**
  (`config/app/`) statt aus der GitHub Container Registry gezogen – dadurch
  laufen die Aenderungen dieses Forks auch wirklich im Container, nicht der
  Original-Code.

## Eigene Funktionen dieses Forks

- **Jalousie-Piktogramm im Fenster-Format** — hochkant wie das
  Loxone-Fenster-Piktogramm (statt Quadrat), mit nur leicht angedeuteten
  Sprossen; die Behang-Animation bleibt unverändert.

- **Fix: Lichtsteuerung zeigte „an", obwohl über eine eigene „Aus"-Szene
  ausgeschaltet.** Ursache: Loxone reserviert intern ID 778 für „aus" — manche
  Anlagen legen aber zusätzlich eine eigene Szene an, die zwar „Aus" heißt,
  aber eine andere ID hat (778 kann parallel existieren, z. B. als
  „Bereich verlassen"). Ein reiner ID-Vergleich erkannte das nicht. Jetzt wird
  zusätzlich der Szenenname „Aus" (Groß-/Kleinschreibung egal) als
  Aus-Kennung erkannt — konsistent auch beim Szenen-Durchschalten (`</>`) und
  beim Einschalten per Kachel-Tap.

- **Neu: `/api/version`** — zeigt den tatsächlich im Container laufenden
  Code-Stand, unabhängig von der Plugin-Version, die LoxBerry anzeigt (die
  kennt nur `plugin.cfg`, nicht den Docker-Build). Auch in der Settings-Seite
  sichtbar (unter dem Verbindungsstatus). Einziger zuverlässiger Weg, ein
  hängendes Docker-Build-Cache-Problem direkt zu erkennen, statt bei jedem
  „das Update wirkt nicht" von vorn zu suchen.

- **Fix: Lichtsteuerung zeigte „an" (gelb), obwohl aus.** Ursache: Loxone
  liefert `activeMoods` manchmal als `[778, 778]` (Aus-Stimmung doppelt) statt
  `[778]` — ein struktureller Listenvergleich wertete das als „an". Jetzt
  inhaltlich geprüft.
- **Fenster bekommen ein eigenes Piktogramm** (Rahmen mit Kreuz, verschwindet
  proportional beim Öffnen) statt des Jalousie-Lamellenstils — gilt für
  Window und WindowMonitor (Sammelmelder, zeigte vorher gar kein
  dynamisches Piktogramm).

- **Tor bekommt ein eigenes Piktogramm** (breiter, auf einer Bodenlinie
  stehend, Segmente statt Lamellen) statt der bisherigen Fenster-Optik.
- **Dimmer**: Lampe wird stufenlos gelb je nach Helligkeit statt Positionsring.
- **Positionsring komplett entfernt** (Client, Server, Config-UI) — Zustand
  zeigt sich jetzt über Piktogramm/Icon-Farbe.

- **Lichtsteuerung: Szenen direkt auf der Kachel durchschalten** — horizontale
  `<` `>`-Mini-Buttons oben rechts (gleiches Design/Farbfeedback wie die
  Jalousie-Tasten), die „Aus"-Stimmung wird dabei übersprungen. Die Glühbirne
  leuchtet gelb, sobald das Licht an ist (egal welche Szene); hat der Baustein
  eine Colorpicker-Subcontrol (RGBW), wird stattdessen deren echte Live-Farbe
  übernommen.
- **Rolladen-Tasten quadratisch** (26×26 px), im Design der Taster-Buttons,
  mit gleichem Farbfeedback (Akzent beim Tippen, 0,8 s grünes Nachleuchten).

- **Fix: Aus-Schalter auf dem Wanddisplay unsichtbar (auf dem Desktop-Browser
  aber sichtbar).** Verdacht: das Muster `rgba(var(--x),alpha)` wird vom
  Kiosk-WebView nicht zuverlässig gerendert (der Ein-Zustand nutzt `var()`
  direkt und war nicht betroffen). Schalter und Taster-Button laufen jetzt
  auf festen Farben statt dieser Kombination — bestätigt nach Cache-Leerung
  weiterhin nötig, kein reines Cache-Problem.
- **Rolladen (Jalousie) bekommen jetzt auch Auf/Ab-Mini-Buttons** oben
  rechts, wie in der Loxone-App — vorher bewusst weggelassen (Touch-Down
  hätte einen Scroll-Wisch kapern können). Jetzt per `click` statt
  `pointerdown` gebunden: löst nur aus, wenn kein Wisch dazwischenkam.
  Während der Fahrt wird die jeweilige Taste automatisch zu „Stop".
- **Taster (Pushbutton):** Kreis größer und kräftiger (Radius, Strichstärke,
  Button selbst), plus 0,8s grünes Nachleuchten nach dem Antippen als
  Bestätigung, dass der Impuls raus ist.

- **Fix: Schnellschalter wieder unzuverlässig (Regression aus 0.12.0).**
  Ursache: eine zu aggressive Absicherung erzwang bei *jeder* Ansicht mit
  Schaltern einen kompletten Neuaufbau, sobald sich irgendein Live-Wert im
  Haus änderte (kommt laufend) — spürbar träge bis hin zu blockierenden
  Ladezeiten. Zurückgebaut auf den effizienten, geprüften Struktur-Abgleich
  (nur neu aufbauen, wenn sich eine Kachel-Struktur tatsächlich ändert).
- **Taster (Pushbutton) bekommen jetzt auch einen Mini-Button.** Bisher hat
  Antippen der ganzen Kachel direkt ausgelöst (keine Detailansicht, kein
  Schnellzugriff wie bei Schaltern). Jetzt wie bei Switch/TimedSwitch: Tap
  auf die Kachel öffnet die Detailansicht mit explizitem „Auslösen"-Button,
  der eigentliche Taster ist ein runder Mini-Button oben rechts — bewusst
  rund statt als Schieber, da ein Taster keinen dauerhaften Ein/Aus-Zustand
  hat.
- **Zurückgenommen:** Bewegungsmelder-Aufwecken (Standby/BWM/Nachlaufzeit)
  und das Pillen-Highlight für den aktiven Tab — beide wieder komplett
  entfernt.

- **Loxone-Touch-Pure-Display-Optik (mit einfachen Mitteln, ohne Komplettumbau):**
  Ring-Regler (Kreisbogen statt Balken, ziehen oder antippen) für die
  Solltemperatur; weichere Kachel-Schatten; Kategoriefarbe jetzt auch im
  Icon-Kreis der Detailansicht (Rand + Icon). Ring-Größe/-Dicke und
  Kachel-Schatten frei im Backend einstellbar (Aussehen, global + pro Panel).
  Neue Standardschrift **Manrope** (Loxones eigene „Objektiv" ist
  kostenpflichtig lizenziert, hätte die Systemoffenheit verletzt) —
  self-hosted im Container, kein CDN/Internet nötig, Docker-Build unverändert
  (kopiert `webfrontend/` ohnehin komplett).
- **Eigene Scroll-Anzeige im Kachel-Raster:** schmaler, dezenter Balken statt
  der von vielen Android-Kiosk-Browsern gar nicht dargestellten
  `::-webkit-scrollbar`. Blendet sich nur ein, wenn tatsächlich mehr Kacheln
  da sind als auf den Screen passen — unabhängig von Geräte-/Layoutgröße.

- **Fix: Intercom-/Kamerabild im Screensaver manchmal nicht angezeigt.**
  Ursache: Viele Türstationen (u. a. DoorBird laut eigener API-Doku) erlauben
  nur wenige gleichzeitige Video-Betrachter. Schließt ein Kiosk-Browser eine
  abgebrochene MJPEG-Verbindung nicht sofort sauber (kommt bei einem
  Dauer-Stream öfter vor als bei einem normalen Bild), blieben serverseitig
  alte Proxy-Verbindungen zur Kamera offen — über mehrere Screensaver-Zyklen
  hinweg konnte sich das ansammeln, bis die Kamera keine neue Verbindung mehr
  annahm. Jetzt: pro Kamera nur noch eine aktive Verbindung gleichzeitig
  (eine neue beendet die alte zuerst), plus Schreib-Timeout, falls der Client
  nicht mehr mitliest.

- **Etwas schnellerer Image-Build:** `--provenance=false --sbom=false` beim
  `docker compose build` spart die standardmäßigen BuildKit-Attestationen
  (Lieferketten-Metadaten) — bei einem rein lokal gebauten und gestarteten
  Image, das nie in eine Registry gepusht wird, ungenutzt, kostete aber
  bislang bei jedem Build 1–2 Sekunden beim Export.

- **Fix: Schnellschalter verschwanden gelegentlich** nach einem Wechsel vom
  Screensaver zur ersten Bedienebene (auf schwächerer Hardware wie dem Shelly
  Wall Display reproduzierbar, auf schnellerem Desktop-Chrome nicht). Ursache:
  `{t:'view'}`-Nachrichten kommen nicht nur bei echter Navigation, sondern
  auch laufend bei jeder Live-Wertänderung im Haus — auf langsamerer Hardware
  können dabei mehrere Nachrichten kurz hintereinander eintreffen, während
  der Screensaver noch überblendet, und die In-Place-Update-Funktion (schnelles
  Patchen ohne Neuaufbau) konnte einen fehlenden Schalter dabei nicht
  nachträglich einfügen. Behoben, indem Ansichten mit Schnellschaltern jetzt
  grundsätzlich immer komplett neu aufgebaut werden statt gepatcht.

- **Screensaver-Vorhersage vergrößerbar:** neues Feld „Screensaver-Vorhersage"
  unter Aussehen (global + pro Panel) — Symbol, Wochentag und Temperatur der
  kleinen Vorhersage-Kacheln skalieren proportional mit. Wirkt jetzt auch bei
  größeren Bildschirmen (ab 640×560px) — dort überschrieb eine zweite, fest
  verdrahtete Regel den eingestellten Wert.
- **Loxone-App-Bedienmuster für Schalter/Zeitschalter:** Tap auf die Kachel
  öffnet jetzt (wie in der offiziellen Loxone-App) die Detailansicht mit
  expliziten Ein-/Ausschalten-Buttons, statt direkt zu schalten. Die
  Schnellschaltung sitzt jetzt oben rechts als echter Schieber (springt
  links/rechts, Farbe zeigt Ein/Aus) statt als Button unten in der Kachel —
  eigene Touch-Zone, löst keine Navigation aus.
- **Screensaver-Antippen löst keine Kachel mehr aus:** zusätzlich zur
  Event-Reihenfolge (click statt pointerdown) jetzt eine 500ms-Sperre nach
  dem Ausblenden für jede Kachel-/Schalter-/Tab-Interaktion — robust
  unabhängig vom genauen Touch-Verhalten des jeweiligen Kiosk-Browsers
  (Event-Reihenfolge allein reichte auf manchen Geräten nicht).
- **Zurück-Pfeil auf jeder Ebene:** erscheint jetzt auch auf der obersten
  Ebene (z. B. Favoriten) und führt von dort zurück zum Screensaver.
- **Favoriten-Kachel** (Config → Panel → Reiter „Favoriten"): frei wählbare
  Bausteine, unabhängig von Raum/Kategorie.
- **Klingelton je Türstation** (Settings → Kamera / Türstation): Panel piept
  mit dem generischen Wecker-Ton, solange der `bell`-Impuls am Miniserver
  ansteht. Default **aus** je Intercom, einzeln aktivierbar.
- **Wecker global abschaltbar** (Config → Global → Darstellung): unterdrückt
  Ton, Aufwecken und automatischen Sprung zur Wecker-Ansicht auf allen
  Panels. Die Wecker-Kacheln selbst bleiben überall normal bedienbar.
- **„Fenster zur Außenwelt"** (Settings → Kalender & Wetter): wird kein iCal
  genutzt, zeigt der Screensaver statt des (leeren) Kalenderbereichs
  wahlweise das Live-Bild einer Türstation/Kamera.
- **Sanfte Animationen** (Settings → Global → Darstellung, an/aus; pro Panel
  unter „Aussehen & Verhalten" überschreibbar — z. B. aus für schwächere
  Panels wie das Shelly Wall Display X1i): Kacheln blenden ein, Screensaver
  faded weich, Zurück-Button poppt sanft ein. Rein GPU-günstige
  Transform/Opacity-Animationen über CSS-Variablen (`--anim-scale` u. a.),
  respektiert zusätzlich `prefers-reduced-motion`.
- **Zurück-Button nur wenn sinnvoll:** erscheint im normalen Tab-Modus nur
  noch, wenn es wirklich ein „Zurück" gibt. Verlässt man den Screensaver zum
  ersten Tab, führt „Zurück" wieder zur Uhr.
- **Eigener Klingelton (MP3-Upload):** je Intercom eine eigene Audiodatei
  (mp3/ogg/wav/m4a/aac, max. 5 MB) hinterlegbar — läuft, solange der
  `bell`-Impuls ansteht. Ohne eigene Datei bleibt es beim generischen
  Wecker-Ton. Läuft über ein **statisches** `<audio>`-Element im Markup (nicht
  dynamisch per JS erzeugt), mit automatischem Fallback auf den Wecker-Ton,
  falls die Wiedergabe blockiert wird — wichtig für Kiosk-Apps wie **Fully
  Kiosk Browser** (z. B. auf einem Shelly Wall Display): deren „Autoplay
  Audio“-Einstellung greift laut eigener Doku nur bei statischen `<audio>`-Tags.
  Diese Einstellung muss dort aktiviert sein, sonst bleibt es stumm.
  „Klingeln testen“-Button je Intercom (Settings → Kamera/Türstation) schickt
  ein echtes Test-Klingel-Event ans gewählte Panel, ohne den Taster zu drücken
  — nutzt jetzt genau den `sound`-Status dieser Intercom (nicht mehr fest
  „an“), meldet also ehrlich, wenn „Ton bei Klingeln“ dort (noch) nicht
  aktiviert/gespeichert ist, statt einen funktionierenden Ton vorzutäuschen.
- **Kachel-Reihenfolge überall frei sortierbar** (Config → Panel): Favoriten,
  Zentral, Räume- und Kategorien-Übersicht nutzen jetzt denselben Mechanismus
  — Ziehgriff, wie App-Icons am Smartphone. Räume/Kategorien zeigen dabei
  gleich Auswahl (welche sichtbar sind) und Reihenfolge in einer Liste, im
  selben Look wie Favoriten (Suche, Icon+Name, Stern/Ziehgriff) — vorher zwei
  unterschiedliche Optiken (Checkbox-Raster vs. Favoriten-Liste) für
  denselben Zweck. **0.10.1:** Bugfix — das Sortieren bei Räumen/Kategorien/
  Zentral hat die neue Reihenfolge bisher nicht gespeichert, sobald die
  interne Ablage dafür noch leer war (u. a. bei jedem allerersten Sortieren).
  Live per Browser-Automatisierung nachgestellt und behoben.

## Was das Plugin macht

- installiert **Docker** (offizielles Docker-Repo) **nur einmalig**, beim
  allererst fehlenden Docker auf dem System — direkt in `preroot.sh`, nicht
  über LoxBerrys eigenen paketbasierten Install-Mechanismus (der würde die
  ~90 MB Docker-Pakete sonst bei *jeder* Installation/jedem Update erneut
  herunterladen und reinstallieren, siehe „Installationsdauer" unten)
- **baut** das Image lokal aus `config/app/` und startet es per `docker compose`
  (Port **8098**)
- startet das Panel beim **Boot** (`daemon`) und prüft alle **5 Minuten**, ob der
  Container läuft (`cron.05min` → `loxpanel-ctl.sh check`)
- sichert die Nutzerdaten bei Updates (`pre-/postroot.sh`)
- entfernt Container + lokal gebautes Image beim Deinstallieren

## Bedienung

Nach der Installation (der **erste** Start dauert wegen des lokalen
Image-Builds ein paar Minuten, kein Reboot nötig):

- **Konfiguration:** `http://<LoxBerry-IP>:8098/config` (Panels, Räume, Kacheln,
  Reiter **„Favoriten"**)
- **Einstellungen:** `http://<LoxBerry-IP>:8098/settings` (Miniserver-Zugang, Intercom, Displays)
- Das LoxBerry-Plugin-Widget leitet direkt auf `/config` weiter.

Der Miniserver-Zugang wird **nicht** im Plugin gesetzt, sondern über die
Einstellungen-Seite und in `data/plugins/loxpanelfav/config/loxpanel.cfg`
(Docker-Volume) gespeichert.

## Installationsdauer

- **Erstinstallation** (Docker fehlt noch): am längsten, weil Docker selbst
  installiert werden muss (~90 MB, einmalig) und das Image ohne Layer-Cache
  komplett neu gebaut wird (Python-Basis + Build-Tools für `cryptography`/`cffi`
  + pip-Abhängigkeiten) — mehrere Minuten sind normal.
- **Updates** (Docker bereits vorhanden, nur Code geändert): deutlich
  schneller, meist unter zwei Minuten — Docker wird **nicht** erneut angefasst,
  und der Image-Build nutzt den Layer-Cache (nur die geänderten Quell-Layer
  werden neu kopiert, die pip-Installation bleibt gecacht).
- Kein Reboot in keinem der beiden Fälle nötig.

## Voraussetzungen

- LoxBerry **3.0+** (Debian Bullseye oder neuer)
- Genug freier Speicher/RAM für einen lokalen Docker-Image-Build (Python-Base-Image
  + pip-Abhängigkeiten); auf einem Raspberry Pi dauert der erste Build ca. 2–5 Minuten.

## Steuerung von Hand (SSH auf dem LoxBerry)

```bash
BIN=/opt/loxberry/bin/plugins/loxpanelfav
$BIN/loxpanel-ctl.sh start      # bauen (falls nötig) + starten
$BIN/loxpanel-ctl.sh stop       # stoppen (bleibt gestoppt)
$BIN/loxpanel-ctl.sh restart    # neu bauen + neu starten
$BIN/loxpanel-ctl.sh check      # starten, falls nicht läuft (Cron/Boot)
```

## Update

Auto-Update ist für diesen Fork **bewusst deaktiviert** (`AUTOMATIC_UPDATES=false`
in `plugin.cfg`), damit er nicht versehentlich vom Original-Repository
überschrieben wird. Um eigenen Code zu aktualisieren: Quellcode in `config/app/`
ändern, `plugin.cfg`-Version hochzählen und das Plugin über LoxBerry neu
installieren (oder `loxpanel-ctl.sh restart`, das baut das Image neu).
