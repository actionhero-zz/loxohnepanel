# Pill

Pillen sind die Tippflächen mit Text: Aktionen, Einstellwerte, Auswahl und Verweise – in genau drei Größen.

## Größen
| Größe | Höhe | Text | Einsatz |
|---|---|---|---|
| **L** | `pill-l` 56 px | 16 px/600 | Hauptaktion der Detailansicht (An/Aus, Modus, Auf/Ab), Alarmanlage, PIN-Tasten |
| **M** | `pill-m` 44 px | 15 px/600 | Einstellen: Wecker/Timer ±, Wochentage, Lautstärke, Intercom-Tasten |
| **S** | `pill-s` 30 px | 13 px/600 | Auswählen und Verweisen: Zeitraum-Chips, Kamerawahl, Verlinkung, Hinweise |

- Radius immer `r-pill` (= halbe Höhe). Keine 10-px-Ecken mehr.
- Nur Symbol: quadratisch-rund mit `min-width` = Höhe (wird damit zum Kreis – passt zur Regel „Bedienelemente sind Kreise“).
- Innerhalb einer Zeile nur eine Größe.

## Zustände
- **normal**: Fläche `tile`, Text `ink`.
- **aktiv** (aktueller Zustand, gewählter Tag/Kamera): Fläche `ink`, Text `tile`.
- **Nebenaktion** (Verlauf, Verknüpft, Quellen): ohne Fläche, Rahmen 1,5 px `ink-2`, Text `ink-2`; schmaler als die Hauptaktionen (Verhältnis 1 : 1,618).
- **Chip** (Auswahl aus mehreren, z. B. Zeitraum): Rahmen 1 px `ink-2`, gewählt wie aktiv.
- **Alarm**: Fläche `crit`, weiße Schrift – nur mit Wort.
- **gesperrt**: 40 % Deckkraft.
- Tippen: `scale(.97)` für `anim-fast`.

## Bestand → neu
| heute | wird |
|---|---|
| `.brow.act .btn` 56 / r 28, `.secpill` 56, `.pinkey` 52 | L |
| `.btn.cht` (Verlauf/Verknüpft) | L, Nebenaktion |
| `.aecol .btn`, `.aedays .btn` 44 / r 22, `.avol .btn` 44 / r 20 | M |
| `.icab` 34 / r 10 (Intercom) | M |
| `.campill` 30 / r 10 (Kamerawahl) | S |
| `.chrng .chip` (Zeitraum) | S, Chip |
| `.sectap`, `.vbell` | S |
| `.ub` 30 / r 10 (Mini ±) | Kreis 30 (`radius-control`) – siehe RoundControl |
| `.camlbl` (Kameraname im Bild) | bleibt Beschriftung, keine Pille |

## Anordnung
- Fuge zwischen Pillen immer `space-gap` (10 px), waagrecht wie senkrecht; die Gruppe steht mittig.
- Hauptaktionen (L) sind gleich breit: eine = 61,8 % der Reihe (goldener Schnitt), zwei teilen die Reihe, ab drei Reihen zu höchstens drei, letzte Reihe mittig.
- Nebenaktionen (Verlauf, Verknüpft, Quellen) sind immer zweitrangig: am Ende rechts, Größe M, nur Umriss, nie gefüllt. Breite 1 : φ zur Hauptaktion; die Hauptaktion behält mindestens die halbe Reihe. Ohne Hauptaktion rechtsbündig, 38,2 % breit.
- Übereinander gestapelte Mini-Buttons (± / ‹ ›) stehen rechtsbündig in der Kachel, Kreise mit 30 px; die Tippfläche ist unsichtbar auf 44 px erweitert.
- **Nebenaktionen nur als Symbol** (seit 0.19.78): Kreis 32 px, Fläche `tile` 55 % ohne Umriss, Tippfläche 44 px, Beschriftung als Tooltip/Screenreader-Text. Symbole: Verlauf `graph-line-3`, Erzwingen `flash-1`, Quellen `playlist-3` (Loxone), Verknüpft eigenes Punkte-Symbol.
