# LoxPanel Favoriten – LoxBerry-Plugin (Docker, eigenstaendiger Fork)

> **Fork von [LoxPanel](https://github.com/Lenardo1/Loxpanel) von Lenardo1.**
> Copyright © 2025–2026 Lenardo1 and LoxPanel contributors (https://github.com/Lenardo1/Loxpanel).
> Lizenz: PolyForm Noncommercial 1.0.0 – nicht-kommerzielle Nutzung, Änderung und Weitergabe
> erlaubt; Details in [LICENSE.md](LICENSE.md). Dieser Fork enthält eigene Änderungen
> (Raster-Editor, Kameras, Dashboard u. a., siehe unten).

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

- **Screensaver frei gestalten (0.14.0)** — Config → Panel-Profil →
  „Screensaver“: Uhr & Datum, Wetter, Kalender, Türstation und Loxone-Kacheln
  per Ziehen & Ablegen im Raster anordnen (3×3 je 480er-Display, 6×3 auf
  breiten Displays wie dem Shelly X2i), Größe an der Ecke ändern. Kacheln
  bleiben im Screensaver bedienbar; die Türstation zeigt nur das Livebild
  (wie das „Fenster zur Außenwelt“, auch als 3×2). Schließen per ✕ und/oder Wischen ↑ ↓ ← → (frei kombinierbar). Ohne
  Belegung bleibt der klassische Screensaver.
- **Farben aus dem Theme (0.19.74)** — Rot, Grün und Gelb, die noch fest im Code standen (Statuspunkte, Löschen-Knöpfe, Fortschritt, Markierungen), kommen jetzt aus den Theme-Farben; Text auf Grün ist weiß.
- **Config-Bausteine vereinheitlicht (0.19.73)** — Popover und Dialoge mit einem Schatten ohne Rahmen, Segmentschalter als Spur mit Pillen, ein Badge-Stil (11 px statt 8 px Versalien), Schalter statt Checkboxen wie im Panel.
- **Einheitliches Design-Raster (0.19.72)** — Rundungen nach goldenem Schnitt und konzentrisch (Karte 36,
  Kachel 22, Innenbox 14, Detail 8), Pillen in drei Höhen (56/44/30) mit halbrunden Enden, Mini-Buttons als
  Kreise, Schrift- und Symbolgrößen auf eine feste Skala ohne Zwischenwerte gebracht – in Panel und Config.
- **Kontraste (0.19.71)** — Icon „an“ (Vorlage bunt), Grün und Hinweis-Gelb der Config erreichen jetzt
  WCAG-Kontrast (3:1 Grafik bzw. 4,5:1 Text). Speichern-Knopf: „Gespeichert“ ohne Haken, schnellere Animation.
- **Alle Loxone-Icons + Miniserver-Härtung (0.19.70)** — Icon-Auswahl „Loxone“ bietet jetzt den
  kompletten Standard-Katalog (550 Icons direkt vom Miniserver, ohne Zusatz-Plugin), lädt beim Scrollen
  nach und findet auch deutsche Begriffe (Licht, Jalousie, Tür …); eigene Icons je Baustein werden mit
  gelistet. Miniserver-Verbindung: Timeout beim Aufbau, lange Pause bei abgelehnter Anmeldung (Schutz
  vor Konto-Sperre), robustes Parsen, Trennungsgrund auf der Startseite. Speichern-Knopf wird grün
  bei Erfolg; Zoom-Effekt auf Tablets korrigiert.
- **Update-Hinweis aktuell (0.19.69)** — Die Config fragt den Update-Stand bei jedem Seitenwechsel neu ab
  (Server puffert 5 min statt 6 h); nach dem Update verschwindet die Pille und die Versionsnummer springt mit.
- **Symbol „Verknüpft“ (0.19.68)** — Neues Symbol (verbundene Punkte), als Linie gezeichnet wie der Verlauf
  statt gefüllt.
- **Tester-Feedback, Tablet-Rundgang, Spenden-Link (0.19.67)** — Sicherungen bleiben bei Plugin-Updates erhalten;
  auf der LoxBerry-Seite herunterladen (⤓) und wieder hochladen. 24 weitere eingebaute Symbole (u. a. Briefkasten,
  Anwesenheit, Haus, Tür, Schloss, Müll, Sonne/Mond). Kamera-Detailseite passt ohne Scrollen; Szenen-/Radiotasten
  füllen die Fläche automatisch (alle sichtbar, min. 64 px). Tablet: Energiefluss passt in die Seite, Status-Wörter
  kleiner als Zahlen, Listen zweispaltig; neues Symbol „Verknüpft“. Config: „Buy me Claude Code Tokens“ unten rechts.
- **Feinschliff Tablet & Knöpfe (0.19.66)** — „Verknüpft“-Pille so klein wie die Verlaufs-Pille. Bedienknöpfe
  (Schalter, Mini-Knöpfe, Regler-Griffe, Player, Zurück, Schließen) wieder rund; Anzeigen bleiben viereckig.
  Breite Detailseiten (Tablet, X2): Lichtszenen im 4er-Raster, 8 Szenen auf einen Blick.
- **Verknüpfte Objekte, eigenes Hintergrundbild, iPad-App-Fix (0.19.65)** — Detailseiten zeigen neben dem
  Verlauf eine kleine Pille „Verknüpft“ (in Loxone Config verlinkte Objekte) → Seite mit den Objekten als Kacheln,
  antippbar auch wenn sie in keinem Tab liegen. Dashboard-Hintergrund wahlweise eigenes Bild (JPG/PNG/WebP,
  Upload in den Dashboard-Einstellungen, leicht abgedunkelt). Home-Bildschirm-App: Ausrichtung frei (Tablets quer),
  Gerätename bleibt erhalten.
- **Tablet: Statusleiste in allen Tabs, harmonische Abstände (0.19.64)** — Auf Tablets/iPad stehen die
  Status-Symbole in jedem Tab unten. Platz verteilt nach festen Regeln: gleiche Ränder oben/unten, Abstände
  zwischen Tab-Leiste, Kacheln und Status-Zeile im goldenen Schnitt (1,618 × Rand), Status-Symbole bündig mit
  der Kachelkante; Dashboard-Leiste und -Raster auf denselben Linien wie in den Tabs.
- **Update-Hinweis, Launcher am Gerät (0.19.63)** — Die Config zeigt unten links eine Pille „Update x.y.z“, sobald
  im Repo eine neuere Version liegt (gleiche release.cfg wie LoxBerrys Auto-Update, 6 h gepuffert); Klick öffnet
  die LoxBerry-Pluginverwaltung. „Launcher einrichten“ (ADB) jetzt direkt in der Steuerung jedes Android-Geräts
  (IP, Name, Ansicht automatisch), statt als Formular unter „Gerät hinzufügen“.
- **Fix Uhrzeit, Tablet-Statussymbole unten (0.19.62)** — Panels zeigten 2 h zu wenig: die Zeitzone „Etc/UTC“
  aus dem Container-Image wird ignoriert, maßgeblich ist der echte UTC-Abstand des LoxBerry. Tablet-Dashboard:
  Leiste mit ✕ bleibt oben, nur die Status-Symbole stehen unten.
- **Tablet: Tab-Namen, Infoleiste unten (0.19.61)** — Auf Tablets/iPad steht unter jedem Tab-Symbol der Name
  (Tab-Leiste 72 px, aktiver Tab als Fläche) und die Statusleiste des Dashboards sitzt unten. Größere Zahlen-Bubble
  in der Statusleiste (82 % des Symbols) auf allen Geräten.
- **Fix Bubble in der Statusleiste (0.19.60)** — Statussymbole nutzen die volle Leistenhöhe; die Zahlen-Bubble
  wird auf dem iPad (größere Symbole) nicht mehr oben abgeschnitten.
- **Geräte umbenennen, größere Tablet-Symbole (0.19.59)** — Gerätename in der Gerätekarte änderbar (Einstellungen
  und Erkennung ziehen mit, verbundenes Gerät übernimmt den Namen sofort). Im Tablet-Zoom Tab-Symbole 36 px,
  Statusleisten-Symbole 29 px.
- **Fix offene Fenster (0.19.58)** — Fensterüberwachung zählt offene/gekippte Fenster aus dem Zustand je Fenster
  (windowStates) statt aus den Zählern numOpen/numTilted, die bei manchen Miniservern auf 0 hängen bleiben.
  Statusleiste und Kachel zeigen wieder „n offen“ mit Bubble.
- **Tablet: Abstand oben, größere Leisten (0.19.57)** — Im Zoom-Modus (iPad/Tablet) rücken Tab- und Statusleiste
  etwas nach unten (Abstand zur iPad-Statuszeile, als Home-Bildschirm-App plus Safe-Area); Leisten 60 px hoch,
  Tab-Symbole 30 px, Statusleisten-Symbole 24 px. Kacheln bleiben quadratisch.
- **Miniserver-Ein-/Ausgänge lesen (0.19.56)** — Neue, rein lesende Admin-Schnittstelle `/api/msio`
  (Zustand eines Ein-/Ausgangs über seinen Namen, Liste der Ein-/Ausgänge) als Grundlage für „Aufwachen bei
  Bewegung“ direkt über Melder-Ausgänge ohne Visualisierungs-Haken.
- **Größere, quadratische Zahlen-Bubbles (0.19.55)** — Bubble 70 % der Symbolhöhe, immer quadratisch (ein- und
  zweistellig gleich groß, zweistellig mit kleinerer Schrift; nur „99+“ etwas breiter); Aussparung im Symbol angepasst.
- **Tablet ohne Balken, inaktive Geräte (0.19.54)** — Gezoomt auf Tablets/iPad füllt die Ebene 0 (Hintergrund,
  Tab-Leiste, Statusleiste) den ganzen Schirm; Kachelfläche, Panes und Dashboard-Raster bleiben quadratisch und
  stehen mittig. Geräte, die sich 30 Tage nicht gemeldet haben, erscheinen blass mit „seit … Tagen nicht gesehen“
  am Ende der Liste.
- **Zahlen-Bubbles „ausgebissen“ (0.19.53)** — Anzahl als viereckige Pille oben rechts am Symbol; das Piktogramm
  darunter bekommt eine Aussparung (Maske), wirkt auf jedem Hintergrund wie ausgebissen. In der Statusleiste und
  auf Kacheln, wo es Sinn ergibt: Fensterüberwachung (offen), Zentral Licht/Audio (aktive Räume), Zentral
  Tore/Fenster (offen). Farben aus dem Design (Glow bzw. Hinweis-Gelb), kurzes Einploppen bei „Animierte Symbole“.
- **Sauberkeit, Geräte löschen, quadratischer Zoom (0.19.52)** — Offene Panels laden nach einem Update selbst neu
  (Code-Kennung), Manifest ungecacht. Kein Zugriffsprotokoll mehr im Log; Backups ohne Fully-APK; Docker-Build-Cache
  wird aufgeräumt; Reste gelöschter Bausteine/Türstationen und lange nicht gesehene Geräte verschwinden automatisch.
  Geräte lassen sich löschen; Kennung aus ?device= wird gemerkt; alte Einträge werden bei Erkennung übernommen.
  Zoom hält Kacheln quadratisch (Rest = Hintergrund). LoxBerry-Seite: Panel-Auswahl für „Web-App öffnen“,
  Updates nur über die LoxBerry-Pluginverwaltung, Umlaute/Schrift korrigiert.
- **Geräte-Erkennung, Serverzeit, LoxBerry-Seite neu (0.19.51)** — Jedes Gerät bekommt eine dauerhafte ID
  (Fully: Geräte-ID, sonst Zufalls-ID in localStorage + Cookie; IP-Wechsel egal) und meldet seinen Steckbrief
  (Bildschirm, Browser, OS, Hardware, bei Fully Modell/MAC). Beim ersten Erkennen legt der Server das Gerät mit
  Namensvorschlag und passendem Gerätetyp an (Shelly, NSPanel, YC-SM41/55, Tablet, iPad, Smartphone, PC);
  Anzeige „Automatisch erkannt“ in der Gerätekarte, neuer Typ „Smartphone“. Panels zeigen die Uhrzeit des
  Servers statt der Geräteuhr. LoxBerry-Seite neu gestaltet (Statuskacheln, Schnellzugriffe, Sicherungen),
  Versionsnummer in der Konfiguration verlinkt GitHub.
- **Kacheln & Pillen, Intercom-Boxen (0.19.50)** — Erkennungszeichen konsequent: alle Kreise (Punkte, Knöpfe,
  Regler, Plaketten, Großsymbol) sind jetzt viereckige Pillen; lange Pillen bleiben. Tab-Einstellungen als
  einklappbare Box wie beim Dashboard. Intercoms je Türstation als eigene Box (Status, Video, Klingelton),
  Klingelton-Bereich aufgeräumt (Status + Knöpfe in einer Zeile, Dateiwahl per Knopf); weitere Kameras darunter.
  Geräte: Fully-Kiosk-Quelle und Hinweise wieder über die volle Breite.
- **Geräte-Optimierung, Standard-Dashboard, aufgeräumte Konfiguration (0.19.49)** — Zoom füllt den ganzen
  Schirm (iPad/Tablet ohne Rand); je Gerätetyp Zoom-Vorgabe und Tipps unter „Einrichtung“ (inkl. Hinweis bei
  falscher Panel-Größe); iPad/Android-Tablet ohne Fully halten den Schirm bis zur Leerlaufzeit wach.
  Dashboard: Vorlagen ersetzt durch „als globale Standardansicht verwenden“ (Vorlage für neue Panels und den
  Assistenten); Einstellungen kompakt in einer Reihe, als Block einklappbar, Statusleisten-Bausteine einklappbar.
  Konfiguration: eine Speicherleiste für alles (Panels, System, Geräte), Karten als Mauerwerk ohne Lücken,
  Kameras/Kalender/„Schrift & Größen“ einklappbar, Miniserver-Felder kompakter.
- **Bausteine ausblenden, Tablet-Zoom, Lichtszenen-Fix (0.19.48)** — Raster-Editor: Seitenleiste in
  einklappbare Bereiche (Größe · Inhalt · Bausteine · Aussehen); bei Raum-, Kategorie- und Zentral-Kacheln
  lassen sich einzelne Bausteine abwählen (in der Web-App ausgeblendet). Zoom je Gerät (Aus/Automatisch/
  Faktor) – 7–8″-Tablets und iPad mini zeigen die 2-Panel-Ansicht formatfüllend; neuer Gerätetyp
  „iPad / iPad mini“. Android-Einrichtung per ADB von der LoxBerry-Seite nach Geräte → Gerät hinzufügen
  verschoben. Lichtsteuerung: Szenenraster passt wieder auf den Schirm. Statusleisten-Plakette mit
  feinem grauem Rand.
- **Handy-Modus, Klingel-Fix (0.19.47)** — Panel-Größe „Handy“ (Profil/Assistent): volle Höhe,
  Tabs unten, Flächen untereinander; Panels passen sich hochkant am Handy automatisch an; als
  Web-App installierbar (Manifest + Symbol). Klingeln: Ende öffnet die Türstation nicht erneut,
  verpasstes Ende (z. B. Laptop im Ruhezustand) wird beim Wiederverbinden aufgeräumt.
  Statusleiste: Anzahl als Plakette am Symbol, Zustände nur über die Symbolfarbe. Raster-Editor:
  Kachel-Einstellungen bleiben rechts. Befehls-Monitoring unter System → Miniserver; Heap-Wert raus.
- **Raster-Editor robust (0.19.46)** — Umbruch nach der tatsächlich verfügbaren Breite (Seitenleiste
  berücksichtigt), bei Größenänderung nur noch Kachelgröße nachziehen statt Neuaufbau; 2 Panels bei
  ~1000 px nicht mehr abgeschnitten; Ziehen flüssiger (Vorschau je Frame/Zellwechsel), sauberer Abbruch
  per Esc/Fensterwechsel, Mitscrollen am Rand; Dashboard-Eigenschaften ragen nicht mehr heraus.
- **Code-Check & Feinschliff (0.19.45)** — Fehler in /api/msstatus behoben (Miniserver-Kennzahlen und
  Live-Zeile der Startseite blieben leer); Helligkeit mit „Automatisch“ (Gerät regelt selbst), Zustand
  wird beim Aufklappen vom Gerät gelesen; Tipp-Töne je Android-Gerät abschaltbar; Befehlsbestätigung
  unter System → Bedienung; Geräte-Aktionen und Fully-Quelle nur, wenn nötig; Bausteinfilter lesbar.
- **Geräte, Statusleiste & Original-Updates (0.19.44)** — Geräte-Seite neu geordnet (Einrichtung →
  Anzeige → Steuerung → Betriebsmodus → Erweitert, nur Benötigtes, mit Symbolen); Fully Kiosk per adb
  installieren (Quelle sichtbar, eigene Adresse oder eigene APK), Display-Helligkeit per adb, Link zum
  Fully Remote Admin; Statusleiste bis 6 Einträge mit eigenen Symbolen (auf 480 px kompakt);
  Widgets in Minimalgröße einfügen; Wetter 3×1 nebeneinander; Bausteinauswahl mit Raum-/Kategorie-
  Filter und Türstationen; Türstation-Widget mit Türöffner/Licht; Versionsstempel (Version · Commit ·
  Installiert) unten in der Konfiguration. Aus LoxPanel 0.7.0: nächtliches Neuladen gegen Einfrieren
  (#82), Detailseiten-Fixes inkl. 0,5er-Schritte (#81), Radiotasten-Ruhetext (#80). Ruhigeres Build-Log.
- **Betrieb & Wartung (0.19.43)** — Container übernimmt die Zeitzone des LoxBerry; Sonnenzeiten für
  Folgetage berechnet (am Miniserver ausgerichtet); Docker-Logs begrenzt (3 × 5 MB); Healthcheck mit
  automatischem Neustart über den 5-Minuten-Cronjob; Build ohne Compiler, wo fertige Pakete
  existieren (x86_64/ARM64), sonst automatisch mit (ARMv7); alte Images werden nach Updates entfernt.
- **Info-Popups einheitlich (0.19.42)** — Status- und Wetter-Popup im gleichen Rahmen (Breite, Kopf,
  ✕ rechts oben) und mit Zoom aus dem angetippten Element; Wetter: Sonnenbogen mit Tageslicht-
  dauer, Einstrahlung je Stunde und aktueller Sonnenposition, Luftdruck-Chip entfernt;
  Dashboard-Symbol mit dünnerem Rahmen.
- **Wetter-Details interaktiv (0.19.41)** — Chips schalten den Graphen um: Temperatur (Start),
  Regen je Stunde, Wind, gefühlte Temperatur, Luftfeuchte, Luftdruck (Stundenwerte des Miniservers);
  Legende und „Einstrahlung max.“ entfernt.
- **Auto-Update aus dem Fork (0.19.40)** — LoxBerry holt neue Versionen selbst aus diesem Repository
  (Plugin-Verwaltung → Update-Modus). Versionen ab jetzt rein numerisch (0.19.40, 0.19.41 …).
- **Wetter-Details im Design (0.19.0-fav39)** — Tagesdetails in den Farben des gewählten Designs,
  Temperaturkurve pastellig nach Temperatur gefärbt (kalt blau, warm apricot/rot); nur Werte des
  Miniservers (zusätzlich Gefühlt, Luftfeuchte Ø, Luftdruck Ø, Einstrahlung max.); Kamera-Umschalter
  transparenter; Dashboard-Symbol größer und feiner.
- **Wetter-Tagesdetails (0.19.0-fav38)** — Wetter-Widget mit optionaler Detailansicht (Haken im
  Widget-Editor): Tipp auf einen Tag öffnet ein Popup mit animierter Temperaturkurve, Regen je Stunde,
  Regenmenge/-risiko, Wind, UV und Sonnenzeiten (Open-Meteo und Loxone-Wetterdienst). Kamera-Umschalter
  als abgerundete Vierecke wie die Minibuttons; Dashboard-Symbol mit dünnerem Rahmen.
- **Dashboard-Symbol mit Panel-Rahmen (0.19.0-fav35, Abstand fav36, größer fav37)** — das Symbol oben links zeigt einen Rahmen im
  Panel-Format (1 Panel quadratisch, 2 Panels 2:1) mit den Kacheln gefüllt darin.
- **Feinschliff (0.19.0-fav34)** — Dashboard-Symbol oben links zeichnet die Kachel-Anordnung des
  eigenen Dashboards nach; Info-Fenster der Statusleiste: Raum fett vorangestellt („**Küche:** Fenster“),
  kein doppeltes „offen“ mehr, nur „gekippt“ als Zusatz.
- **Symbole & Bedienung (0.19.0-fav33)** — eigene Symbole in Pastellgelb (Plugin + Web-App: Kacheln
  mit Favoriten-Stern, Backend: Kacheln mit Reglern) als Favicon und Plugin-Icon; Klick auf „LoxPanel“
  im Backend führt zur Startseite; Player-Tasten und Favoriten lösen erst beim Tippen aus, Wischen
  scrollt (aus LoxPanel #66).
- **Startseite & Geräte (0.19.0-fav32)** — Miniserver-Kachel mit Kennzahlen (CPU, Heap, Tasks,
  Antwortzeit, Firmware); Geräte als Chips wie die Panels, Panels-Kachel mit Anzahl; unter Geräte jede
  Kachel einzeln und einklappbar, neu erkannte Geräte oben und aufgeklappt; Info-Fenster der
  Statusleiste listet Einträge untereinander.
- **Farbverlauf im Dashboard (0.19.0-fav31)** — Hintergrund und/oder Uhrzeit-Schrift wahlweise nach
  Tageslicht (nachts dunkel, Dämmerung warm, mittags hell) oder Außentemperatur (blau → grün → gelb →
  orange/rot); Einstellung je Panel unter Dashboard → Farbverlauf, Standard: feste Design-Farben.
- **Verbindungsüberwachung (0.19.0-fav30)** — Hinweisbalken am Panel, wenn Miniserver oder
  LoxPanel-Server nicht erreichbar sind (Werte werden blass, Bedienung bleibt frei); keepalive alle
  30 s mit Neuaufbau toter Verbindungen; Ping Panel↔Server; Miniserver-Kachel der Startseite mit
  Live-Status; optionale Befehlsbestätigung (System → Miniserver). Verlauf-Diagramme teilen sich
  die Pane-Höhe (aus LoxPanel #60). Einleitungstext der Startseite entfernt.
- **Detailansichten aus einem Guss (0.19.0-fav29)** — kein Scrollen mehr durch das
  Hintergrund-Symbol und keine stehengebliebene Scroll-Anzeige; Kopf ohne doppelten/leeren Raum;
  Energiemanager/-monitor mit Kennzahl-Kacheln, Eigenverbrauch plausibel; klare Texte (Ein/Aus,
  Kein Alarm, Taster „Bereit“, Präsenz auf Deutsch, Wecker-Tage mit Trennzeichen); Zentral-Listen
  aktive zuerst mit weicher Blende; Betriebsart-Pfeil in einer Zeile.
- **Backend aufgeräumt (0.19.0-fav28)** — System mit 7 Reitern (Kategorie-Farben unter
  Darstellung, „Kameras“), Profil neu gegliedert (Allgemein · Bildschirm · Display & Nacht ·
  Alarm), Bedienung in einer Karte, Audio-Einstellungen vor dem Test-Ton; Auswahlfelder nicht
  mehr abgeschnitten, alle Eingabefelder im Design, kompakte Handy-Ansicht; Speicherleiste
  nach „Rückgängig“ korrekt; Statusseite zeigt Meldungen zuerst.
- **Fixes (0.19.0-fav27)** — Szenennamen im Lichtbaustein wieder lesbar (CSS-Kollision),
  ohne %-Anzeige; Bildausschnitt auch für weitere Kameras, Editor nur bei Bedarf (schont
  Browser-Verbindungen) mit Widget-Rahmen; Öffnen-Pfeil direkt an jedem Panel in der Liste.
- **Statusleiste-Feinschliff (0.19.0-fav26)** — Statusleiste per Haken an/aus mit kompakter
  Bausteinauswahl; schematisch im Grid-Editor angedeutet; Einbrennschutz (Drift) gilt jetzt
  auch für die Menüleiste und läuft unabhängig von der Animations-Einstellung.
- **Dashboard mit Statusleiste (0.19.0-fav25)** — Dashboard im Tab-Rahmen mit Menüleiste:
  Statusleiste (bis 4 Bausteine, neutral bis etwas passiert; im Grid-Editor unter
  Dashboard-Eigenschaften, unabhängig vom Ampel-Widget) und ✕; Wetter-Widget passt in
  alle Größen; Fensterliste mit Raum; vom Dashboard geöffnete Bausteine markieren keinen Tab.
- **Animierte Symbole (0.19.0-fav24)** — neuer Haken „Animierte Symbole“ (global, je Panel
  überschreibbar): Klingel/Wecker/Alarm wackeln, Jalousie-Pfeil wippt beim Fahren, Heizung
  pulsiert beim Heizen, Symbol ploppt beim Einschalten, neue Werte ticken ein, Ampel-Wechsel
  wird kurz hervorgehoben.
- **Feinschliff (0.19.0-fav23)** — Alarm-Vollbild neu (ganzer Bildschirm, Detail-Kopf, alle
  Tasten als gleich große Pillen in einer Reihe, leichte Animation); Status-Ampel mit Schrift und
  Form im Kachel-Standard; Fensterdetails zeigen offene Fenster zuerst.
- **Alarm-Ton (0.19.0-fav22)** — optionaler Piepton zum Alarm-Vollbild je Panel; Ton wird beim
  ersten Antippen freigeschaltet und fällt bei Sperre auf eine erzeugte WAV zurück (Tablets,
  NSPanel, Shelly, Fully); gilt auch für Klingel- und Weckton.
- **Alarm-Vollbild & Türstation (0.19.0-fav21)** — Alarmanlage/Rauchmelder lösen ein rotes
  Vollbild mit Stumm/Quittieren/Unscharf aus (je Panel unter Profil wählbar); Türstation mit
  Bildausschnitt (Fokus/Zoom, System → Intercom) und Tasten als Pillen auf dem Livebild;
  Status-Ampel passt sich standardmäßig dem Design an; „Zurück“ führt wieder zum Dashboard.
- **Status-Ampel (0.19.0-fav20)** — neues Widget „Status“: bis zu 4 Bausteine aus Loxone
  (Fenster, Alarm, Rauch, Briefkasten, Statusbausteine) als Ampel mit Chips; Tipp öffnet die
  Status-Seite bzw. den Baustein; Wetter-Widget standardmäßig 3 Tage Vorhersage.
- **Wetter-Fix (0.19.0-fav19)** — Wettervorschau im Widget passt immer in ihre Kachel,
  Schriftgröße der Vorschau auf 8–32 begrenzt; Panel-Assistent mit passenden Vorlagen-Namen
  bei 1 Panel.
- **Assistenten (0.19.0-fav18)** — Panel-Assistent beim Anlegen (Größe, Tabs, Dashboard,
  Design, Name, Gerät) oder leer anlegen; Betriebsmodus-Assistent (aus dem Original
  übernommen); Panel löschen per ✕ in der Liste; Speicherleiste zeigt die einzelnen Änderungen.
- **Schnelle Kameras (0.19.0-fav17)** — Umschalten im Kamera-Widget ohne Wartezeit (bis 3
  Kameras laufen parallel, Server hält Kameras 60 s verbunden); neues Panel startet auf der
  Profilseite mit Standardraster 2×2.
- **System aufgeräumt (0.19.0-fav16)** — Hauptmenü Start · System · Geräte; unter System:
  Sicherheit (Passwortschutz), Darstellung global, Nachtmodus in „Bedienung“, Wetterquelle bei
  „Miniserver“; Datum/Uhr folgen der Sprache der Konfiguration; Vorschau-Tage am Wetter-Widget;
  „Display & Nacht“ klarer gegliedert; Icon-Auswahl im Raster-Editor nicht mehr abgeschnitten.
- **Sicherheit & breite Kamera (0.19.0-fav15)** — Icon-Abruf nur noch für echte Icons,
  Schutz vor Befehlen fremder Webseiten, optionaler Passwortschutz der Konfiguration
  (Startseite → Zugriffsschutz; Zurücksetzen auf der LoxBerry-Plugin-Seite); Kamera-/
  Intercom-Widget bei zwei Panels auch in Tabs über beide Panels (4×2 bzw. 6×3).
- **Schneller & schlanker (0.19.0-fav14)** — Neustart/Update ca. 10 s schneller (Server
  schließt Verbindungen sofort), kleineres Plugin-Paket, schlankeres Docker-Image; Größen im
  Raster-Editor immer wählbar (sucht freien Platz oder sagt, warum nicht); Intercom-Widget
  ebenfalls über beide Panels.
- **Kamera-Auswahl (0.19.0-fav13)** — im Kamera-Widget Kameras per Haken wählen und per
  Ziehen sortieren; im Dashboard mit zwei Panels auch über beide Flächen (bis 6×3);
  Kamera-Zeilen in den Einstellungen schneiden Benutzer/Passwort nicht mehr ab.
- **Kameras (0.19.0-fav12)** — eigene Überwachungskameras neben den Intercoms
  (System → Intercom / Kameras), neues Widget „Kamera“ mit Pillen zum Durchschalten;
  eine Kamera-Verbindung für alle Betrachter mit automatischem Neuaufbau (behebt das
  „hängende“ Kamerabild, wenn ein zweites Gerät zuschaut).
- **Moderne Bedienung (0.19.0-fav11)** — Startseite mit Status und Einrichtungs-Checkliste,
  Suche/Befehlspalette (Strg/⌘+K), Rückgängig statt Rückfragen, Speicherleiste mit
  Änderungszähler und Strg/⌘+S, ?-Hilfe statt langer Texte, schrumpfende Kopfzeile;
  Kachel-Einstellungen im Raster-Editor bleiben rechts und scrollen mit.
- **Upstream-Fixes & responsive (0.19.0-fav10)** — aus Lenardo1/Loxpanel: Energiefluss
  (Speicher-Richtung, Hausverbrauch), alte Raumregelung (IRC v1) mit Kachel/Detailseite,
  Betriebsart-Auswahl, Speichern meldet nicht Übernommenes; Config für alle Fenstergrößen
  (Handy bis 4K), Raster-Editor passt die Kachelgröße an.
- **Editor-Feinschliff (0.19.0-fav9)** — Tab löschen per ✕ am Tab; Kachel-Aussehen auch
  für Raum- und Kategorie-Kacheln der Übersichten; schlankere Seitenleiste im Raster-Editor.
- **Aufgeräumt & fließendes Layout (0.19.0-fav8)** — Config-Inhalt passt sich der
  Fensterbreite an; Dashboard-Widgets über beide Displays (z. B. Uhr mittig); verwendete
  Widgets in der Bibliothek markiert; alter Code und tote Styles entfernt.
- **Dashboard im Tab-Editor (0.19.0-fav7)** — Dashboard und Tabs in einem Bereich mit
  demselben Raster-Editor; Tab-Leiste wie am Panel (Dashboard links, Tab 1 rechts, per Ziehen
  umsortieren); einklappbare Seitenleiste; Meine Geräte: Status, Knöpfe und Einstellungen je
  Gerät in einem Block; Übersicht Räume/Kategorien direkt im Raster ein-/ausblenden.
- **Neuer Raster-Editor & Look (0.19.0-fav6)** — Tab-Raster mit Bibliothek (Suche,
  Bausteine direkt hineinziehen), Live-Vorschau wie am Panel, Tauschen beim Ablegen,
  ✕/Entf, Strg+Z; Config im Look der Web-App mit Theme Bunt/Hell/Dunkel; Gerätetyp je
  Gerät (steuert die Neustart-Knöpfe); Hauptmenü Start · System · Geräte · Darstellung.
- **Aufgeräumt & adb-Neustart (0.19.0-fav5)** — Config aufgeräumt (doppelte Optionen
  entfernt, klarere Namen, Sprache/Test-Ton an sinnvollem Ort); Fully neu starten und
  Gerät neu starten per adb (ohne Fully-PLUS-Lizenz).
- **Mehrfach-Tabs & Designer (0.19.0-fav4)** — Übersicht Räume/Kategorien und Zentral
  mehrfach anlegbar (eigener Name, eigene Auswahl); Standardraster im Profil; Display &
  Nacht und Feinjustierung im Profil; Zusatzfläche je Tab entfällt (Widgets im Raster);
  Kachel-Designer direkt im Raster-/Dashboard-Editor.
- **Übersichten & Menü (0.19.0-fav3)** — Übersichten Räume/Kategorien als Raster-Tabs
  (Auswahl in den Tab-Eigenschaften, Reiter „Räume & Kategorien“ entfällt); Raster-Editor
  wächst nach unten wie am Panel; Hauptmenü nur global (Start · Darstellung · Geräte ·
  System), einzelne Panels über die Seitenleiste.
- **Raster & Profil (0.19.0-fav2)** — Tabs und Dashboard wahlweise im 2×2- oder
  3×3-Raster; Reiter „Profil“ mit Panel-Größe (1 Panel 480×480 / 2 Panels 960×480);
  eigene Symbole je Tab; Tab-Editor mit Tab-Leiste und Seiten nebeneinander;
  „Screensaver“ heißt jetzt „Dashboard“; Detailseiten wieder im 2×2-Raster.
- **Freie Tabs & neue Config (0.19.0-fav1)** — Bis zu 4 Tabs auf dem 3×3-Raster
  wie der Screensaver: Frei, Raum, Kategorie oder Zentral (vorbefüllt aus Loxone,
  per Ziehen & Ablegen anpassbar, neue Bausteine kommen automatisch dazu) sowie
  Übersichten Räume/Kategorien. Kacheln 1×1/2×1/2×2, Widgets, mehrere Seiten.
  Config neu gegliedert (Start · Panels gestalten · Geräte · System), doppelte
  und veraltete Optionen entfernt. Fully Kiosk per Knopf neu starten.
- **Lichtszenen & Kontrast (0.18.0-fav2)** — Option „Lichtfarbe & Helligkeit
  anzeigen (lernend)“: Szenen-Symbol mit Kern in Lichtfarbe und 0–3 Ringen für die
  Helligkeit, lernt jede Szene beim ersten Einschalten. Option „Mehr Kontrast“
  (weicher Schatten an Kacheln/Knöpfen). Grün/Rot-Text auf hellen Designs besser lesbar.
- **Spezialbausteine (0.18.0-fav1)** — Alarmanlage/Rauchmelder mit farbiger
  Zustandsfläche, Türstation mit Livebild über die ganze Karte, Tor wie die
  Beschattung, Wecker mit Bearbeiten-Seite, Audio mit Cover im Hintergrund und
  Lautstärke-Balken, Lüftung, Bewässerung, Energie, Protokoll, Zentral-Seiten;
  PIN-Eingabe im Kartenstil.
- **Detailkopf & Pillen (0.17.0-fav5)** — Raum und Bausteinname oben auf jeder
  Detailseite; reine Anzeigen mit übergroßem, blassem Piktogramm im Hintergrund;
  alle Knöpfe der Aktionsreihe als gleich hohe Pille.
- **Leiste & Verlauf (0.17.0-fav4)** — Animation in drei Stufen (Keine/Mittel/
  Viel, global und je Panel); links Dashboard-Symbol bzw. Zurück-Pfeil; kompakte
  Leiste mit bis zu 3 antippbaren Pfad-Symbolen; Verlauf immer als eigene Seite
  über 📈 in der Aktionsreihe; Anzeigeseiten mit kleinem Piktogramm über dem
  großen Wert.
- **Flüssiger auf dem Shelly (0.17.0-fav3)** — Zoom über eine einzige Fläche
  (nur transform/opacity statt Seitenkopie + clip-path), Kacheln blenden nur
  ein, kein Helligkeitsfilter beim Antippen, Szenen scrollen ohne Ruckeln,
  Bildlaufanzeige und Uhren ohne unnötiges Neuzeichnen.
- **Einheitliche Detailseiten (0.17.0-fav2)** — alle Bausteine nach demselben
  Standard: Zustand groß, Wert+Regler als Fläche, Knöpfe in der Aktionsreihe,
  Verlauf auf eigener Seite (📈). Heizung: Soll als Fläche, Modi Eco/Komfort/
  Auto. Schalter/Taster neu, Auswahlschalter als Kacheln. Pfad-Symbole
  antippbar, Lichtszenen scrollbar ohne Auslösen.
- **Detailseiten & Leiste nach Mockup (0.17.0-fav1)**
  - Leiste: Zurück links im Tab-Look, Tabs rechtsbündig (Tab 1 ganz rechts),
    daneben Pfad-Piktogramme (antippbar, springen auf die Ebene).
  - Lichtszenen als 2×2-Kacheln; Aktionsreihe je nach Baustein (Aus, alle
    Leuchten gemeinsam dunkler/heller in 10-%-Schritten).
  - Klima ohne Ring-Regler: große Ist-Temperatur, Ziel, − / +.
  - Beschattung: hoch · Stellung (Füllstand) · runter; Dimmen: Fläche = Regler.
  - Große Zahlen auf allen Detailseiten (Nachkommastelle kleiner/heller).
  - Sofortige Rückmeldung beim Antippen, Puls bis zur Bestätigung.
- **Shelly-Fixes (0.16.0-fav2)** — helle Designs werden von Androids WebView
  nicht mehr automatisch abgedunkelt (`color-scheme`); Zoom ohne Aufblitzen
  des Rahmens und ohne doppelte Einblendung der Kacheln.
- **Neuer Look nach UI-Mockup (0.16.0-fav1)** — Tab-Leiste oben, darunter eine
  abgerundete Karte je Tab in eigener Farbe mit weißen Kacheln (480×480 und
  960×480). Design-Vorlagen Bunt (Standard) / Dunkel / Hell, jede Farbe per
  Farbwähler änderbar (Aussehen → Design). Zoom-Übergang Kachel ↔ Detailseite.
  Schrift für Zahlen & Titel frei wählbar, Standard Sora (self-hosted, OFL).
- **Screensaver-Widgets aus dem Original 0.6 (0.15.0-fav3)** — Wetter-Details,
  Energiefluss, Verlauf (Baustein + Zeitraum) und Audio (Cover, Steuerung,
  Lautstärke) frei im Screensaver-Raster.
- **Aktiv-Overlay entfernt (0.15.0-fav3)** — den Zustand zeigen Piktogramme,
  Icon-Farben und Mini-Buttons; Alarm/Störung bleiben fest rot bzw. grün.
- **Screensaver-Raster in der Visu-Fläche (0.15.0-fav2)** — das eigene Raster
  liegt wie der klassische Screensaver genau über der Visu statt über dem
  ganzen Browserfenster; die Zellen bleiben dadurch quadratisch.
- **Übernahmen aus dem Original LoxPanel 0.6.0 (0.15.0-fav1)**
  - Miniserver-Anmeldung wird automatisch erneuert (vorher kamen nach 1–2
    Tagen keine Befehle mehr an); gescheiterte Befehle zeigt das Panel an.
  - Bis zu 8 Kalender (iCal-Abos) mit Name und Farbe; mehrtägige Termine an
    allen Tagen; gestrichene, abgesagte und verschobene Serientermine
    korrekt (verschobene zusätzlich im Fork); Google-Serien mit UNTIL gehen
    nicht mehr verloren; weniger Abrufe (iCloud-Sperre, Retry-After).
  - Verlaufs-Diagramme: Detailseite, Split-Hälfte und Mini-Verlauf in der
    Kachel (Config → Kacheln gestalten → Verlauf).
  - Kleinere Fehler: Monatskalender-Wochentage, Energiefluss-Icons in
    WebViews, Kontrast der Raumzeile, leere Port-Variable.
- **Screensaver-Kacheln wie im Raster (0.14.0-fav4)** — mit Raumname und in
  denselben Schrift-/Piktogrammgrößen wie die übrigen Kacheln; lange Namen
  brechen mit Silbentrennung auf zwei Zeilen um.
- **Farbige Lichter gut erkennbar (0.14.0-fav3)** — das Piktogramm einer
  RGB-Lichtsteuerung übernimmt die Live-Farbe mit Mindesthelligkeit: tief
  gedimmte Szenen (z. B. „Nacht“) bleiben dunkler, verschwinden aber nicht mehr.
- **Screensaver-Feinschliff (0.14.0-fav2)** — keine doppelte Uhr mehr in der
  Mitte (Split-Panels), Türstation als ruhiges Livebild ohne Buttons (neu auch
  3×2), größere Vorschau-Kacheln und Piktogramme im Wetter-Widget.
- **Kamera stabiler (0.14.0)** — Kamerabilder werden bei Rückkehr ans Panel
  neu aufgebaut (friert nach langer Ruhe nicht mehr ein), bei Fehlern nach 8 s
  erneut versucht; optional je Türstation automatischer Neuaufbau alle
  6/12/24 h (Einstellungen → Kamera / Türstation).
- **LoxBerry-Seite:** Panel-Profil als Freitext, darunter die übergebene URL.

- **Android-Panel per Klick einrichten (optional, 0.13.11)** — LoxBerry-Pluginseite →
  „Android-Panel einrichten“: Gerät (Shelly Wall Display / anderes Android-Tablet
  als Testing) und Panel-IP wählen, der Container installiert per ADB den
  LoxPanel-Launcher (`android/panel-launcher`) und trägt die LoxBerry-Adresse
  ein. Beim Shelly wird er Startbildschirm (Symbole „LoxPanel“ und „Shelly“),
  auf anderen Tablets erscheint er im App-Menü. Fully Kiosk ist kommerziell und
  wird nicht mitgeliefert – die Einrichtung prüft, ob es installiert ist.
  Voraussetzung: ADB über WLAN am Panel aktiv; beim ersten Mal „USB-Debugging
  zulassen“ am Panel bestätigen.

- **Code-Check & Härtung (0.13.9)** — Miniserver-/Kamera-Passwort wird bei
  geändertem Host/Benutzer bzw. URL nicht mehr weiterverwendet; Cover-Proxy
  liefert nur noch Bilder (max. 5 MB); Agent-Anmeldung prüft IP/Port; Agent
  startet Chromium nie doppelt und kodiert die Profil-ID; eine fehlerhafte
  Kachel reißt nicht mehr die ganze Seite mit; Loxone-`keepalive` auf dem
  Miniserver-WebSocket; Verbindungs-Aufräumen an einer Stelle.

- **Licht per Doppeltipp aus** — Doppeltipp auf eine eingeschaltete
  Lichtsteuerungs-Kachel sendet den Loxone-Aus-Befehl (`changeTo/778`).
  Eigene Tipp-Erkennung (350 ms), funktioniert auf Touch (Shelly Wall Display,
  Tablets) und mit Maus. Abschaltbar unter Einstellungen → Global → Bedienung.

- **Fenster-Piktogramm auch für generische Fensterkontakte** (InfoOnlyDigital
  mit Fenster-Icon) — wie in der Loxone-App am zugewiesenen Icon
  (`window-*.svg`) erkannt. Offen/zu kommt aus den in Loxone Config
  hinterlegten Texten (ganze Wörter, „gekippt" zählt als offen); ist das nicht
  eindeutig, bleibt das normale Icon. Geschlossen mit Sprossen, offen ohne.

- **Rollladen-Piktogramm wie im Loxone-Webinterface** — Geometrie 1:1 aus
  dem Loxone-SVG übernommen (gefüllter Hochformat-Rahmen, Behang als voller
  Block, der je nach Stellung von oben hereinfährt), Farbe aus dem Theme.

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

## Aufbau des Repos

| Pfad | Inhalt |
|---|---|
| `plugin.cfg`, `release.cfg`, `*.sh`, `daemon/`, `cron/`, `sudoers/`, `uninstall/` | LoxBerry-Plugin-Rahmen (Installation, Start, Update) |
| `bin/loxpanel-ctl.sh` | Docker-Steuerung (start/stop/check/backup/restore) |
| `webfrontend/htmlauth/index.cgi` | Plugin-Seite in der LoxBerry-Oberfläche |
| `config/docker-compose.yml` | Container-Definition (Port 8098) |
| `config/app/bin/` | Server (`webvisu.py`) und seine Module – das läuft im Container |
| `config/app/webfrontend/` | Panel, Config-Editor, Settings (HTML/JS) |
| `config/app/android/` | Fertig gebauter LoxPanel-Launcher (APK), wird per ADB installiert |
| `android/panel-launcher/` | Quellcode + Build-Skript des Launchers |
| `config/app/agent/`, `config/app/deploy/` | Panel-Agent und Installer für Linux-Anzeigegeräte |
| `config/app/tools/` | Entwickler-Diagnoseskripte (nicht im Image) |

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
