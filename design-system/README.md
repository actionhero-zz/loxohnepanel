tilebert ist eine Loxone-Visualisierung für Wandpanels ab 480 × 480 px (ein LoxPanel Fork von Lenardo1). Ruhig, freundlich, pastellig: ein dunkler Rahmen, darauf je Tab eine farbige Karte, darauf weiße Kacheln. Alles ist zum Antippen gemacht – mit dem Finger, aus einem Meter Abstand.

## Ebenen
- **Ebene 0 – Dashboard und Screensaver:** das Dashboard-Tab mit Infoleiste. Der Screensaver ist dieselbe Ebene.
- **Ebene −1 – Popups:** Alarme und Infos aus der Infoleiste. Sie legen sich bei Bedarf über Ebene 0, 1 und 2.
- **Ebene 1 – Tabseite:** die Karte `face-*` mit dem Raster. **2×2 ist Standard** für neue Panels, 3×3 ist möglich (bestehende Profile ohne Angabe bleiben 3×3). Die Zellen füllen die Karte bis auf den Innenabstand, ohne Seitenrand, und haben je Gerät ein einheitliches Seitenverhältnis (Panel ca. 1,2 : 1, Handy 1 : 1). Hier wird gewählt und überblickt, nicht eingestellt.
- **Ebene 2 – Baustein**, in zwei Formen:
  - **2a Kachel:** der Baustein im Raster mit Symbol, Raum, Name und einem Zustand. Tippen öffnet 2b. Direkt auf der Kachel schalten nur ihre **Schnellbedienungen**: Mini-Schalter (Ein/Aus), Mini-Buttons ‹ › (Stimmung/Helligkeit) und ˄ ˅ (Jalousie, Fenster). Bausteine ohne eigene Detailansicht (z. B. reiner Taster) lösen beim Tippen ihren Loxone-Befehl direkt aus.
  - **2b Detail:** derselbe Baustein geöffnet. Aufbau: Kopf, großer Wert, Einträge, Aktionen. Hier wird eingestellt.
  - **2b-Unterseite:** Was eine eigene Seite braucht (Verlauf, verknüpfte Bausteine, Quellen), öffnet über einen Nebenaktions-Knopf rechts oben im Kartenkopf (siehe „Nebenaktionen“). Ebenso öffnen **Einträge mit Pfeil ›** eine Unterseite (z. B. Wecker → Eintrag bearbeiten, Raum → Baustein). Unterseiten haben denselben Kopf wie 2b, Zurück geht genau eine Ebene zurück, Änderungen gelten sofort. Die Verschachtelung folgt der Struktur des Loxone-Bausteins; eigene zusätzliche Ebenen werden nicht erfunden.

## Grundsätze

- **Einheitliches Seitenverhältnis je Gerät:** Alle Rasterzellen eines Bildschirms haben dieselbe Form (2×1 = doppelt so breit, 2×2 = vier Zellen inkl. Fuge). Auf Panels ergibt sich das Verhältnis aus der Karte (480×480: etwa 1,2 : 1, die Zellen füllen die Karte ohne Seitenrand), auf dem Handy sind die Zellen quadratisch und es wird senkrecht gescrollt.
- **480 × 480 muss immer funktionieren.** Das Grundraster ist 3 × 3 Zellen à `cell` (160 px). Tablets (iPad mini, 7″) bekommen Anpassungen nur im gezoomten Modus (`sqfit`/`sqbig`), nie auf Kosten von 480 × 480.
- **Hardwareunabhängig.** Keine Gerätegesten, kein Hover als einzige Bedienung, keine Schatten im Panel.
- **Farben kommen aus dem Theme.** Nie Literalfarben in Komponenten: immer `tile`, `ink`, `ink-2`, `face-*`, `dot-*`, `on`, `good`, `crit`. Ein Nutzer kann jede Farbe in Config → Aussehen → Design umstellen; neue Elemente müssen das mitmachen.
- **Neue Kacheln und Widgets** übernehmen Schrift, Größen, Farben, Radius und Innenabstand der bestehenden Kacheln (`r-l`, `space-tile`, `tile-name`, `room-label`).

## Inhalt und Ton

- Sprache Deutsch, Du-frei und knapp: Beschriftungen sind Substantive oder Zustände („Deckenlicht“, „an · 80 %“, „Fenster offen“), keine Sätze.
- Raum steht in Versalien über dem Namen (`room-label`), der Name darunter (`tile-name`), maximal zwei Zeilen.
- Werte mit Komma und schmalem Abstand vor der Einheit: „21,5 °C“, „1,8 kW“. In der Detailansicht ist die Nachkommastelle samt Einheit 60 % groß und in `ink-2`.
- Config-Rückmeldungen nennen das Ergebnis: „✓ Gespeichert (2 Bereiche)“, „Fehler: …“. Keine Entschuldigungen.
- Keine Emojis in der Oberfläche. Einzige Ausnahme: das Kaffeetassen-Symbol der Spenden-Pille.

## Farbe

- **Rahmen** `bezel` mit `bezel-ink`/`tab-idle` darauf. Der aktive Tab ist eine Fläche `tab-active` mit `tab-active-ink`.
- **Karte** je Tab: `face-1` … `face-5`, ab Tab 6 `face-n`. Der passende Akzent heißt gleich: `dot-1` gehört zu `face-1`. Pastellgelb (`face-1` / `dot-1`) ist der Markenakzent.
- **Kachel** immer `tile` mit `ink` (Name, Wert) und `ink-2` (Raum, Einheit, Zweitzeile).
- **Eingeschaltet:** Symbol in `on`. Bei Szenen und Schaltleisten kippt die Fläche: Hintergrund `ink`, Schrift `tile`.
- **Status:** `good` / `crit` nur zusammen mit Wort oder Symbol. Eine Störung kippt die Kachel zusätzlich in die gefüllte Form – Farbe allein reicht nicht (rot-grün-blind).
- **Config** hat eigene, feste Farben (`cfg-*`): heller Lavendelgrund, weiße Karten, dunkler Hauptbutton, aktive Navigation in `cfg-active`.
- Drei Vorlagen: **bunt** (Standard), **dunkel**, **hell**. Der Server leitet bei eigener Grundfarbe alle Werte her und prüft Kontraste (Hauptschrift 7:1, Rest 4,5:1, Grafik 3:1).

## Typografie

- Zwei Familien, beide selbst gehostet: **Manrope** (`text`) für alles Lesbare, **Sora** (`num`) für Zahlen, Uhr, Titel der Detailansicht und Szenen.
- Große Werte `value-hero`, Uhr `clock`, Kachelname `tile-name` (Gewicht 450), Raum `room-label`.
- Ziffern immer `font-variant-numeric: tabular-nums`, damit Werte beim Aktualisieren nicht springen.

## Form: Kacheln und Pillen

- **Rundungen nach goldenem Schnitt, konzentrisch:** Karte `r-xl` (36) − Kartenabstand `space-card` (14) = Kachel `r-l` (22); darin Innenboxen `r-m` (14), Details `r-s` (8). Jede Stufe ist etwa φ (1,6) kleiner. Neue Elemente nehmen die Stufe ihrer Ebene, nie einen eigenen Wert.
- **Schrift** nur aus der Skala 10 · 11 · 12 · 13 · 14 · 15 · 18 · 20 · 22 · 26 · 30 px; **Symbole** 16 · 24 · 32 · 44 px.
- **Tippflächen** mindestens 44 px (Pille M), Abstand zwischen Tippflächen mindestens 8 px. Kleinere Bedienelemente (Mini-Buttons 30 px, Schalter 38×22) bekommen eine unsichtbar erweiterte Tippfläche.
- **Symbole:** Loxone-IconsFilled vom Miniserver; eigene nur, wo Loxone keins hat (Pfeile, Plus/Minus, Ein/Aus, Verlauf, Verknüpft, Liste, Ordner).
- **Schrift nie unter 11 px**, auch nicht in Badges.
- **Indikatoren** (Statuspunkt, Zahlenbadge, Hero-Symbol der Detailansicht) sind abgerundete Quadrate mit `radius-round` (32 %). Keine Kreise. Zahlenbadges bleiben quadratisch, auch zweistellig.
- **Lange Pillen** bleiben lang (`r-pill`): Verlinkungs-Pille, Filter, Config-Buttons.
- **Bedienelemente bleiben Kreise** (`radius-control`): Schalterknopf, Mini-Buttons, Regler-Daumen, Player-Tasten, Zurück, Schließen.
- Zwischen Kacheln `space-gap`, in der Kachel `space-tile`, Karte zum Rand `space-frame`.

## Detailansicht-Schema
- Reihenfolge immer, einspaltig untereinander (auch auf 960 × 480): **Kopf** (Raum in Versalien klein, darunter der Bausteinname) → **großer Zustand** (eine kurze Zeile darunter) → **Einträge** → **Aktionen**.
- Der große Wert ist der **Ist-Zustand**: Licht „An/Aus“ (siehe Auswahlbausteine), Heizung die Ist-Temperatur (Sollwerte darunter, Verstellen mit −/+), Sensor die Zahl mit Einheit (Loxone-Text wie „sehr gute Luftqualität“ als Zeile darunter), Alarm „Scharf/Unscharf/Alarm“.
- **Seiten mit Eintragsliste** (Licht-Stimmungen, Radio, Fenster/Türen, Bewässerungszonen, Zentral-Mitglieder): Zustand als EINE Zeile direkt unter dem Kopf (die bisherige Unterzeile wird zum Zusatz) – Zustandswort in Sora 22–30 px `ink`, dahinter „· aktive Auswahl“ in 60 % Größe `ink-2`, einzeilig mit „…“. Mix: „An · A, B“. Keine aktive Stimmung bekannt: nur „An“ bzw. „Aus“. Die große Hero-Stufe bleibt Zahlen ohne Liste (Sensor, Heizung) und Alarm. Die Aus-Stimmung steht nur als Aus-Knopf in der Aktionsreihe, nie zusätzlich in der Liste; bei Licht aus nennt die Zeile ihren Namen („Aus · Bereich verlassen“), sofern er nicht „Aus“ lautet. Die Liste scrollt beim Öffnen/Wechsel zur ersten aktiven Zeile (Reihenfolge wie in Loxone; nicht, solange der Nutzer gerade selbst gescrollt hat). Einen „An“-Knopf gibt es nicht – Loxone hat dafür keinen Standardbefehl, eingeschaltet wird über eine Szene.
- Ist der Zustand ein Text statt einer Zahl (Taster „Zuletzt ausgelöst“), steht er kleiner (`value-hero` · Stufe 22–30 px), die Zeit darunter.
- Zustandsfarbe des großen Werts nur aus dem Theme: heizt = Wärme-Token (`dot-3`), kühlt = kühler Token, ruht = `ink`.
- Zusatzangaben (Betriebsart, Zeitplan, „Fenster offen“) als Chips unter dem Wert: Anzeige = transparent mit Haarlinie, tippbar = gefüllt mit Pfeil ˅/›.
- Heizung wie der Rollladen aufgebaut: −/+ als runde Bedienelemente direkt links/rechts neben der Ist-Temperatur (wie ˄/˅ bei der Jalousie), darunter EINE ruhige Textzeile in `ink-2` („Soll 24,0° Komfort · Ruht · Ziel 22,0°“) plus nur die tippbaren Menü-Chips (z. B. „Automatik nur Heizen ˅“); optional die Zeitleiste 0–24 Uhr mit Komfortzeiten aus dem Loxone-Zeitplan; Betriebsarten als Pillen unten. Keine eigene Sollwert-Fläche.
- Alles passt auf ein Panel (960 × 480, 480 × 480) ohne Scrollen; Verläufe füllen den freien Platz, bei zu wenigen Messwerten steht „Noch zu wenig Messwerte“.
- Einträge (Lichtszenen, Zonen, Wecker, Ausgänge, Stimmungen) sind Listenzeilen: 46 px hoch (Tablet 52 px), `r-m`, Symbol links, Titel und Unterzeile, aktiv gefüllt in `ink`.
- **Standard zwei Spalten:** Auf Panels und Tablets stehen Einträge in zwei gleich breiten Spalten über die ganze Breite (480 × 480 ab 3 Einträgen, breit immer) – Lichtszenen genauso wie Bewässerungszonen. Nie drei Spalten (einzige Ausnahme: Handy quer, zu wenig Höhe); Handy hoch eine Spalte. Zeilen mit Zustandswort rechts (Fenster) auf 480 × 480 einspaltig, damit die Namen lesbar bleiben. Passen nicht alle Einträge, scrollt die Liste senkrecht – der Rest der Ansicht bleibt unverändert. Nie seitwärts scrollen.
- Kamera „ganzes Bild“: freie Ränder in Kartenfarbe oder als verwischtes Bild – nie weiße Streifen.

## Nebenaktionen
- Knöpfe, die eine Unterseite öffnen (Verlauf, Verknüpft, Quellen), stehen **rechts oben im Kartenkopf** der Detailansicht und ihrer Unterseiten, auf Höhe von Raum + Name – auf allen Geräten gleich. Raum + Name bleiben mittig.
- Form: Kreis 44 px (`radius-control`), Fläche `tile` 55 %, ohne Umriss, Symbol 22 px, mit Beschriftung als Tooltip. Abstand 8 px. Reihenfolge von rechts: Verlauf, Verknüpft, Quellen.
- **Höchstens zwei sichtbar.** Bei mehr: Verlauf plus „⋯“ mit Menü (Popup-Standard). Ein Knopf wird nie weggelassen.
- Sofortbefehle (z. B. „Erzwingen“ der Bewässerung) sind keine Nebenaktion, sondern Pillen in der Aktionsreihe.
- Die Aktionsreihe unten enthält nur Hauptaktionen. Die Kopfleiste (Zurück, Pfad, Tabs) bleibt reine Navigation.

## Sammelbausteine (Zentral-Licht, -Rollladen, -Alarm, -Audio, Fenster/Türen)
- Kachel und Detail nennen denselben Zustand mit denselben Worten („2 offen · 1 gekippt“, „3 Räume an“, „0 von 2 scharf“) – keine Festtexte wie „Beschattung“.
- Steht der Zustand als Wort in der Zeile (rechts, „offen“/„gekippt“ in `ink` fett, Ruhezustand in `ink-2`), gibt es keinen Indikator-Punkt. Der Punkt bleibt Zeilen ohne Zustandstext vorbehalten.
- Zeilen, die einen Einzelbaustein öffnen, sind gefüllt mit Pfeil ›; reine Anzeigen nur Haarlinie – nie gemischt.
- Abweichler stehen oben (offen/an vor zu/aus); Unterzeile nur der Raum.
- Sammelaktionen (Alle aus, Alle auf …) als Pillen unten, nur Loxone-Standardbefehle.

## Kacheltext und Seiten
- **Gemeinsame Grundlinie:** Der Textblock der Kachel hat drei feste Plätze – Raumzeile, Name (Platz für zwei Zeilen, sonst „…“), Zustand unten. Kacheln einer Reihe stehen dadurch bündig, egal ob der Name ein- oder zweizeilig ist.
- **Seiten:** Raster, die mehr als eine Bildschirmhöhe brauchen, werden exakt in Seiten geschnitten (keine angeschnittene Folgereihe). Die Position zeigen **Seitenpunkte** rechts in einer eigenen Spur (9 px, aktiv `ink` 75 %, sonst 32 %) – einen klassischen Scrollbalken gibt es im Kachelraster nicht.
- **Aufbau fest:** Piktogramm oben links, darunter Raum, Name, Zustand unten auf der festen Zustandslinie. Rechts oben gehört ausschließlich der Schnellbedienung (bzw. dem Sensor-Pfeil); keine Zustandsangaben neben dem Piktogramm. In Raumansichten bleibt der Platz der Raumzeile reserviert, Name und Zustand stehen an derselben Stelle wie im Favoriten-Tab.
- **Werte groß (Option):** Reine Wert-Kacheln (Zahl + Einheit, ohne Bedienung) zeigen den Wert kachelfüllend: Sora 600, tabular-nums, auf allen Wert-Kacheln eines Bildschirms GLEICH groß (22,5 % der Zellbreite, ≈ 49 px bei 216 px), Einheit hochgestellt mit 32 % der Wertgröße in `ink-2`; Raum + Name klein einzeilig oben links; Piktogramm als Wasserzeichen rechts unten (8 %). Texte bleiben normal. Globale Option wie Animation/Kontrast (System → Darstellung → Effekte: „Werte groß auf Kacheln“ An/Aus, Standard aus), am Panel „Wie Standard / An / Aus“, je Kachel überschreibbar (Panel-Standard / immer groß / nie groß).
- Kachel-Bedienelemente: Mini-Buttons 30 px, Schalter 38 × 22, je mit unsichtbar erweiterter Tippfläche. Eingeschaltet ist **eine** Farbe: Schalter, Symbol und Zustand in `on`.

## Popups
- **Blatt** (Status, Wetter, PIN): Hintergrund abgedunkelt, mittig, `r-xl` (sehr hoch: `r-l`), Kopf 56 px mit Titel links und Schließen-Kreis rechts (≥ 44 px Tippfläche). Breite 440 px auf 960 × 480 (breiter Inhalt 720), sonst Bildschirm − 32 px; Höhe nach Inhalt, auf Panels ohne Scrollen. Zeilen nach „Fläche heißt tippbar“, Aktionen als Pillen L, aktiv `ink`. Schließt über ✕, Tippen daneben, Wischen nach unten (Handy) und immer beim Navigieren.
- **Menü** (Auswahl an einem Knopf): `r-m`, Einträge 44 px, mind. 160 px breit, aktive Wahl `ink`; schließt bei Wahl oder Tippen daneben.
- **Hinweis** (Meldung, Verbindung, Test-Ton): oben, `r-m`, Theme-Schrift, Stufenfarbe als Token, nicht tippbar, verschwindet selbst.
- **Vollbild nur für Alarm:** über allem, schließt nur über „Ausblenden“ oder eine Aktion. Die Klingel bleibt ein Hinweis in der Türstation.
- Reihenfolge von hinten nach vorn: Menü < Blatt < Hinweis < Alarm < Nachtabdunklung.

## Fläche heißt tippbar
- Alles Tippbare hat eine Fläche; der Rang zeigt sich an Größe und Deckkraft: Hauptaktion `tile` deckend (aktiv `ink`), Nebenaktion (Kreis 44 px, rechts oben im Kartenkopf) und Chips `tile` 55 %, ohne Umriss.
- Reine Anzeigen (z. B. Bewässerungszonen) haben keine Fläche, nur eine Haarlinie. „Läuft/aktiv“ zeigt eine leichte Tönung plus Indikator-Quadrat in `dot-*` – nie die dunkle `ink`-Füllung, die ist Bedienelementen vorbehalten.
- Einträge, die eine Ansicht öffnen, sind Bedienelemente und tragen rechts einen Pfeil ›.
- Keine eigene Logik: Was ein Eintrag kann, bestimmt allein der Loxone-Baustein (Standardbefehle).

## Bewegung

- Dezent und abschaltbar: alle Dauern sind `anim-*` × `--anim-scale`; „Animationen aus“ in der Config bzw. `prefers-reduced-motion` setzt 0. Neue Animationen hängen an `html.ianim`.
- Kachel-Einblendung nur über `opacity` (schwache Panel-Hardware wie Shelly). Tippen: `scale(.97)`. Zoom Kachel → Detail `anim-zoom`.

## Ikonografie

- Kachelsymbole sind Linien-Icons (24er Raster, Strich 1,7, runde Enden) in `currentColor`; die Kachel färbt sie über `ink-2` bzw. `on`.
- Loxone-Icons (IconsFilled, ~550, vom Miniserver) werden per CSS-Maske in derselben Farbe gezeigt – nie als buntes Bild.
- **Regel Hintergrund-Piktogramm:** Detailansichten von **Anzeigen ohne Schaltelemente** (Sensoren, Zustände, Messwerte) tragen das Bausteinsymbol übergroß im Hintergrund – 85 % der kleineren Kartenseite, links unten, bewusst angeschnitten (rund zwei Drittel sichtbar), 8 % Deckkraft. Es lockert die sonst leere Seite auf. Nie hinter Bedienelementen, nie bei Bausteinen mit Schaltern/Pillen.

## Config

- Zwei Ebenen: dunkle Seitenleiste (`cfg-bezel`) und heller Inhalt (`cfg-bg`) mit Karten (`cfg-panel`, `r-l`, `shadow-cfg`) in Masonry-Spalten.
- Eine gemeinsame Speicherleiste unten. Der Speichern-Knopf ist `cfg-prim`; bei Erfolg wird er 2 s grün mit „✓ Gespeichert“, bei Fehler rot.
- Lange Einstellungsblöcke sind zusammenklappbar; selten Genutztes eingeklappt.
- Die Config ist für PC/Monitor optimiert (kein Touch-Zwang für Tippflächen).
- **Speichermodell:** Primär (`cfg-prim` gefüllt, Schrift `prim-ink`) ist nur „Speichern“ in der Speicherleiste – und „Weiter“ in Assistenten. Alles andere ist Nebenaktion: Fläche `field`, Rand `line`, Schrift `fg`. Sofort wirkende Aktionen (Test-Ton, Passwort, Log, Geräteaktionen …) tragen ein kleines Blitz-Symbol (11 px) mit Hinweis „Wirkt sofort“. Gefährliches (Löschen, Entfernen, Zurücksetzen): Schrift `crit`, rote Kontur, keine Füllung, rechts abgesetzt bzw. in eigener Zeile mit Trennlinie, immer mit Rückfrage.
- **Auswahl:** Ausgewählt = 2 px Ring in `prim` (ohne Layoutsprung) plus Häkchen-Quadrat 18 px (`radius-round`) oben rechts in `prim`, Häkchen in `prim-ink`; an Pillen als 16-px-Marke an der Ecke. Kleine Wahlfelder (< 44 px) und Tab-Chips nur Ring. Akzent-/Orangetöne sind für „ausgewählt“ nicht erlaubt.
- **Karten:** Eine einzelne Karte füllt die Breite; Text steht immer in Karten; jeder Aufklapper trägt denselben Pfeil ›. Hilfe „?“ öffnet ein schwebendes Popover (`r-m`) statt Inhalt zu verschieben.

## Logo

Der Name steht immer klein geschrieben: **tilebert**. Die Marke sind vier Kacheln (Gelb, Blau, Koralle, Mint) mit Augen und Mund. Dateien unter `logo/`, Vorschau und Regeln in der Komponente **Logo**.

- **Marke** `logo/marke.svg` (mit Mund) ab 32 px; darunter (16–31 px) `logo/marke-klein.svg`.
- **Einfarbig:** `marke-einfarbig-tinte.svg` auf hellem, `marke-einfarbig-weiss.svg` auf dunklem Grund – nur wenn Farbe nicht möglich ist.
- **Wortmarke** `wortmarke-hell.svg` (Grund hell) und `wortmarke-dunkel.svg` (Grund dunkel): Sora 600, klein, Laufweite −3 %, als Kurven; mindestens 100 px breit.
- **Schutzzone:** eine Kachelkante `s` rundum frei.
- **Favicons:** Web-App = gelbe Kachel mit Auge (`logo/favicons/webapp/`), Konfiguration = blaue Kachel mit Schalter (`logo/favicons/konfig/`).
- **Farben:** Tinte `#1f2440`, Gelb `#ffc145`, Blau `#7db7ff`, Koralle `#ff9e7a`, Mint `#5cd6a4`. Nicht umfärben, strecken oder drehen.
