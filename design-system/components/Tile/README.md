# Tile

Die Kachel ist das Grundelement: ein Baustein (Licht, Fenster, Wert) auf einer Tab-Karte.

## Aufbau
- Fläche `tile`, Radius `r-l`, Innenabstand `space-tile`; liegt immer auf einer `face-*`-Karte.
- Oben links das Symbol (`ink-2`, eingeschaltet `on`), oben rechts optional ein Indikator.
- Unten Raum (`room-label`), Name (`tile-name`, max. 2 Zeilen), optional Zweitzeile (`sub`).

## Zustände
- **aus**: Symbol `ink-2`. **an**: Symbol `on`, Zweitzeile nennt den Zustand („an · 80 %“).
- **Störung**: Kachel kippt in die gefüllte Form `crit` mit weißer Schrift – nie nur Farbe am Symbol.
- Tippen: `scale(.97)` für `anim-fast`. Langes Tippen öffnet die Detailansicht (Zoom `anim-zoom`).

## Größen
1×1, 2×1, 2×2 Zellen. Im 3×3-Raster schrumpft der Name bei 1×1 und 2×1 auf 80 %.
