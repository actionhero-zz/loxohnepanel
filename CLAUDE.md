# LoxPanel Favoriten – Regeln für Claude

LoxBerry-Plugin „LoxPanel Favoriten“ (Fork von Lenardo1/Loxpanel), läuft als eigener
Docker-Container (Port 8098). Server: `config/app/bin/webvisu.py`, Config-Seite:
`config/app/webfrontend/html/config.html`, Panel: `config/app/webfrontend/html/`.
Ausführliche Übergabe: `docs/UEBERGABE-LOKAL.md`.

## Stil
- Antworten Deutsch, ultrakurz.
- Code-Kommentare deutsch **ohne Umlaute**, knapp. UI-Texte mit Umlauten über `T('…')`.
- Vor jedem Commit kurz den Nutzer fragen.

## Arbeitsteilung (zwei Instanzen)
- **Cloud-Instanz (claude.ai/code): nur der adb-/Android-Teil.**
  - `android/panel-launcher/**` (Launcher-App, `build.sh`, `launcher.keystore`)
  - `config/app/android/**` (fertige APK + `.version`)
  - adb-Funktionen in `webvisu.py`: `_adb`, `api_panel_launcher`,
    `api_panel_launcher_version`, `App.launcher_version`, `App.kiosk_restart`,
    `App.fully_install`, `App.device_brightness`, `App.device_touch_sound`,
    `App.device_adblog` und ihre `/api/kiosk/*`, `/api/panel/launcher*`,
    `/api/device/adblog`-Handler
  - Config-Seite: Geräte-Abschnitte „Einrichten per adb“, Helligkeit/Tipp-Töne,
    Geräte-Log (`devLauncherVer`, `devBrightness`, `devTouchSound`, `deviceAction`
    für `launcher`/`fullyinstall`/`kioskrestart`/`devreboot`)
- **Lokale Instanz (Mac): alles andere** – Panel, Bausteine, Config, Theme,
  Statusleiste, Diagnose, Docker usw. **und alle Releases.**
- Muss eine Seite etwas im Bereich der anderen ändern: nur das Nötigste, im Commit
  klar benennen.

## Git / Release
- Cloud pusht **nur** auf den Branch `claude/adb` – keine Versionsnummer, kein
  Changelog, kein main. Changelog-Vorschlag steht im Commit-Text.
- Lokal: `git fetch origin claude/adb && git merge origin/claude/adb`, dann Release:
  1. Version erhöhen in `plugin.cfg`, `release.cfg`, `APP_VERSION` (webvisu.py)
  2. Changelog-Eintrag ganz oben in `README.md` unter „Eigene Funktionen dieses
     Forks“ (neueste zuerst, nichts angepinnt): `- **Titel (0.19.x)** — Text`
  3. `python3 -m py_compile config/app/bin/webvisu.py`
  4. Commit `0.19.x: Titel`, push `main` (+ `claude/adb` nachziehen)
  5. Plugin-ZIP: `git archive --format=zip --prefix=loxpanelfav/ -o loxpanelfav-0.19.x.zip HEAD`
- Commit-Autor: `actionhero-zz <najrefisch@googlemail.com>`.

## Android-Launcher
- APK nur in der Cloud bauen (`android/panel-launcher/build.sh`, braucht Debian-
  Pakete `aapt apksigner zipalign dalvik-exchange android-sdk-platform-23` + JDK).
- `launcher.keystore` nie ersetzen – sonst klappt `adb install -r` nicht mehr.
- Bei Änderungen `versionCode`/`versionName` im Manifest erhöhen; `targetSdkVersion` ≥ 24.
