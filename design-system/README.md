LoxPanel ist eine Loxone-Visualisierung für Wandpanels ab 480 × 480 px. Ruhig, freundlich, pastellig: ein dunkler Rahmen, darauf je Tab eine farbige Karte, darauf weiße Kacheln. Alles ist zum Antippen gemacht – mit dem Finger, aus einem Meter Abstand.

## Grundsätze

- **Ebene 1 immer quadratisch:** Kacheln sitzen in quadratischen Rasterzellen (1×1 = 1:1, 2×1 = 2:1, 2×2 = 1:1, jeweils inkl. Fuge) – auf jedem Gerät; auf dem Handy richtet sich die Zeilenhöhe nach der Spaltenbreite, mehr Inhalt wird senkrecht gescrollt.
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
- Reihenfolge immer: Kopf (Raum, Name) → Zustand (großer Wert, eine Zeile darunter) → Einträge → Aktionen.
- Einträge (Zonen, Wecker, Ausgänge, Stimmungen) sind Listenzeilen: 46 px hoch (Tablet 52 px), `r-m`, Symbol links, Titel und Unterzeile, aktiv gefüllt in `ink`. Schmal eine Spalte, breit zwei gleich breite Spalten über die ganze Breite. Nie seitwärts scrollen.
- Kamera „ganzes Bild“: freie Ränder in Kartenfarbe oder als verwischtes Bild – nie weiße Streifen.

## Fläche heißt tippbar
- Alles Tippbare hat eine Fläche; der Rang zeigt sich an Größe und Deckkraft: Hauptaktion `tile` deckend (aktiv `ink`), Nebenaktion (Kreis 32 px) und Chips `tile` 55 %, ohne Umriss.
- Reine Anzeigen (z. B. Bewässerungszonen) haben keine Fläche, nur eine Haarlinie. „Läuft/aktiv“ zeigt eine leichte Tönung plus Indikator-Quadrat in `dot-*` – nie die dunkle `ink`-Füllung, die ist Bedienelementen vorbehalten.
- Einträge, die eine Ansicht öffnen, sind Bedienelemente und tragen rechts einen Pfeil ›.
- Keine eigene Logik: Was ein Eintrag kann, bestimmt allein der Loxone-Baustein (Standardbefehle).

## Bewegung

- Dezent und abschaltbar: alle Dauern sind `anim-*` × `--anim-scale`; „Animationen aus“ in der Config bzw. `prefers-reduced-motion` setzt 0. Neue Animationen hängen an `html.ianim`.
- Kachel-Einblendung nur über `opacity` (schwache Panel-Hardware wie Shelly). Tippen: `scale(.97)`. Zoom Kachel → Detail `anim-zoom`.

## Ikonografie

- Kachelsymbole sind Linien-Icons (24er Raster, Strich 1,7, runde Enden) in `currentColor`; die Kachel färbt sie über `ink-2` bzw. `on`.
- Loxone-Icons (IconsFilled, ~550, vom Miniserver) werden per CSS-Maske in derselben Farbe gezeigt – nie als buntes Bild.
- Im Hintergrund der Detailansicht steht das Symbol übergroß, links unten angeschnitten, 8 % Deckkraft.

## Config

- Zwei Ebenen: dunkle Seitenleiste (`cfg-bezel`) und heller Inhalt (`cfg-bg`) mit Karten (`cfg-panel`, `r-l`, `shadow-cfg`) in Masonry-Spalten.
- Eine gemeinsame Speicherleiste unten. Der Speichern-Knopf ist `cfg-prim`; bei Erfolg wird er 2 s grün mit „✓ Gespeichert“, bei Fehler rot.
- Lange Einstellungsblöcke sind zusammenklappbar; selten Genutztes eingeklappt.
