# tilebert (früher LoxPanel) – Regeln für Claude

LoxBerry-Plugin „tilebert“ (früher „LoxPanel Favoriten“; ein LoxPanel Fork von Lenardo1/Loxpanel), läuft als eigener
Docker-Container (Port 8098). Server: `config/app/bin/webvisu.py`, Config-Seite:
`config/app/webfrontend/html/config.html`, Panel: `config/app/webfrontend/html/`.
TbView (eigene Kiosk-App): `docs/TBVIEW.md`.

## Stil
- Antworten Deutsch, ultrakurz.
- Code-Kommentare deutsch **ohne Umlaute**, knapp. UI-Texte mit Umlauten über `T('…')`.
- Vor jedem Commit kurz den Nutzer fragen.

## Arbeitsort
- Seit 2026-10-10 alles auf claude-pi (`/home/dietpi/projekte/loxohnepanel`), inkl. Android/adb.
  Teile dürfen in die Cloud ausgelagert werden. Commit/Push/Release macht ein günstiger Agent.
- Testserver: Docker `lpdev` (Port 8099, Quellcode eingebunden), Browser-Tests mit Chromium +
  `~/projekte/tools/browser/*.mjs`. Shelly X2i Test-Gerät: 192.168.1.247 (adb).

## Git / Release
- Release nur auf „commit“ des Nutzers, ausgeführt von einem günstigen Agenten:
  1. Version erhöhen in `plugin.cfg`, `release.cfg`, `APP_VERSION` (webvisu.py)
  2. Changelog-Eintrag ganz oben in `README.md` unter „Eigene Funktionen dieses
     Forks“ (neueste zuerst, nichts angepinnt): `- **Titel (0.19.x)** — Text`
  3. `python3 -m py_compile config/app/bin/webvisu.py`
  4. Commit `0.19.x: Titel`, push `main` und Spiegel `claude/festive-sagan-avv9if`
     (alte Installationen lesen dort `release.cfg`; Spiegel bleibt, bis alle ≥ 0.19.114 haben)
  5. Plugin-ZIP: `git archive --format=zip --prefix=loxpanelfav/ -o loxpanelfav-0.19.x.zip HEAD`
     nach `~/projekte/releases/`, dann Tag `v0.19.x` + GitHub-Release mit dem ZIP
- Commit-Autor: `actionhero-zz <najrefisch@googlemail.com>`.

## Android-Launcher / TbView
- APK auf dem Pi bauen: `android/panel-launcher/build.sh` (aapt, apksigner, zipalign, JDK,
  dazu `~/projekte/tools/android/{p28/android.jar,r8.jar}`). TbView: `docs/TBVIEW.md`.
- `launcher.keystore` nie ersetzen – sonst klappt `adb install -r` nicht mehr.
- Bei Änderungen `versionCode`/`versionName` im Manifest erhöhen; `targetSdkVersion` ≥ 24.
