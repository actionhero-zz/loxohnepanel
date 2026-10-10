# LoxPanel Favoriten – Architektur-Übersicht (Nachschlagewerk)

Stand: Version 0.19.114, Arbeitsbaum mit uncommitteten Änderungen (2026-10-10). Zeilennummern = Arbeitsbaum, driften bei Edits;
bei Zweifel `grep -n`. Pfade relativ zu `/home/dietpi/projekte/loxohnepanel`. Kürzel: `W` = `config/app/bin/webvisu.py`,
`P` = `config/app/webfrontend/html/panel.html`, `C` = `.../config.html`.

## 1. Gesamtbild

```
Browser/Kiosk (P) <--WebSocket /ws + HTTP--> webvisu.py (aiohttp, Port 8099 im Container, 8098 am Host)
Config-Browser (C) <--HTTP /api/*-----------> webvisu.py <--WS/HTTP--> Loxone Miniserver (loxone_ws.py, loxone-api)
                                                        <--WS 7091--> Audioserver (audioserver*.py)
                                                        <-- iCal / Open-Meteo (front_info.py)
Android-Panel: TbView/Kiosk.java (WebView) lädt P; Server installiert APK per adb.
```

### LoxBerry-Plugin (Repo-Wurzel)
| Datei | Zweck |
|---|---|
| `plugin.cfg` | NAME/FOLDER=`loxpanelfav` (nie ändern!), VERSION, AUTOUPDATE (RELEASECFG auf GitHub `main`), ARCH, REBOOT=false |
| `release.cfg` | VERSION + ARCHIVEURL (main.zip); muss bei jedem Release hoch (SemVer rein numerisch) |
| `preroot.sh` | root, vor Install: Docker nachinstallieren, Container stoppen, Config+Backups nach `/tmp` sichern, `bin/version.json` (Commit/Zeit) stempeln |
| `postroot.sh` | root, nach Install: Config/Backups zurückspielen, Container per `loxpanel-ctl.sh start` (als `loxberry`) |
| `preupgrade.sh`/`postupgrade.sh` | No-ops (Logik liegt in pre/postroot) |
| `daemon/daemon` | Boot: `loxpanel-ctl.sh check` |
| `cron/cron.05min` | alle 5 min `loxpanel-ctl.sh check` (Neustart, wenn Container unerwartet weg; bewusst gestoppt bleibt aus) |
| `bin/loxpanel-ctl.sh` | start/stop/restart/check/backup/restore; `REPLACELBP*`-Platzhalter werden beim Install ersetzt |
| `config/docker-compose.yml` | Service `loxpanelfav`, `build: ./app`, Port `8098:8099`, Volume `REPLACELBPDATADIR/config:/app/config`, Healthcheck `/api/version` |
| `webfrontend/htmlauth/index.cgi` | Perl-LoxBerry-Seite: Status, Miniserver übernehmen, Panel einrichten (Android/Shelly), Backups/Log; spricht den Container per `.cgi_token` an (W:10924) |
| `sudoers/`, `uninstall/` | sudo-Rechte für docker, Aufräumen |
| `icons/icon.svg`, `design-system/` | Plugin-Icon bzw. Design-Tokens/Komponenten-Doku (nicht Laufzeit) |

### Docker (`config/app/`)
- `Dockerfile:1-49`: python:3.12-slim, `requirements.txt` (loxone-api/aiohttp/cryptography), `adb` aus apt, `COPY . .`, `ENV LOXPANEL_PORT=8099`, `CMD python bin/webvisu.py`.
- Persistenz nur `/app/config` (Volume): `loxpanel.cfg`, `panels.json`, `theme.json`, `devinfo.json`, `scene_light.json`, `pushlog.json`, `diag.log*`, `sounds/`, `bg/`, `adb/` (adbkey + Fully-APKs), `.cgi_token`.
- Mitgeliefert: `android/LoxPanel-Launcher.apk` + `.version` (versionCode), `agent/` (Linux-Panel-Agent), `deploy/` (kiosk.sh, systemd), `tools/` (Diagnose-Skripte, nicht im Image: `.dockerignore`).
- Testserver: Docker `lpdev` Port 8099 mit eingebundenem Quellcode (siehe CLAUDE.md).

### Android-Launcher / TbView (`android/panel-launcher/`, Java ohne Gradle)
- `build.sh` (aapt/javac/r8/apksigner/zipalign) → schreibt `config/app/android/LoxPanel-Launcher.apk`; `launcher.keystore` nie ersetzen; bei Änderungen `versionCode`/`versionName` im `AndroidManifest.xml` (aktuell 6 / 5.1).
- `src/de/loxpanel/launcher/`: `Main.java` (Moduswahl tbview|fully), `Kiosk.java` (426 Z., WebView + JS-Brücke, Näherung/Licht/Helligkeit; `@JavascriptInterface` ab Z.347), `Fully.java`, `Home.java`/`StockHome.java` (HOME-Launcher-Altbestand).
- JS-Brücke `window.TbView` (Kiosk.java:347-403): `turnScreenOn/Off`, `isScreenOn`, `getDeviceId`, `setDisplayOff`, `setSaver`, `setDisplayBrightness(%)`→bool, `setAutoBrightness(on,min,max)`, `setProximityWake`, `getProximity`, `getLightLevel`, `getDeviceInfo`, `reload`. App→Panel: `window.lpHost._ev('prox'|'light'|'screen', wert)`.
- Details/Gerätetests: `docs/TBVIEW.md`. Panel-Seite: `lpHost` (P:4141), `applySensors` (P:5913), `applyNight` (P:5875).

## 2. Server `config/app/bin/webvisu.py` (11 192 Z.)

### Nachbarmodule
| Datei | Inhalt |
|---|---|
| `loxone_ws.py` (328) | `LoxoneWS` (:103): Binär-WS zum Miniserver (Value-/Text-/Weather-States, Keepalive), `describe_close`, `format_uuid` |
| `loxone_weather.py` (470) | Wetter aus Miniserver-Wetterserver (Kennung 7) → gleiche Form wie `front_info.fetch_weather`; `build` (:234), `sun_times` (:136) |
| `front_info.py` (852) | Kalender (iCal, RRULE/EXDATE, `fetch_events` :535) + Open-Meteo (`fetch_weather` :625), `load_front` (:766) |
| `adapters.py` (132) | `LightControllerV2Adapter`, `JalousieAdapter` (alt, `W:184-185`: `LIGHT`, `JAL`) |
| `audioserver.py` (125) | `LoxoneAudioServerBackend` (Befehle, WS 7091), `make_backend` (:115) |
| `audioserver_auth.py` (93) | Gen-2-Anmeldung (RSA/AES-JWT) |
| `audioserver_events.py` (435) | `AudioEventClient` (:41): Now-Playing/Favoriten per Push |
| `theme_colors.py` (442) | `derive(grundfarbe)` (:276) WCAG-Theme aus einer Farbe, `DESIGN_PRESETS/KEYS`, `clean_design` (:389), `design_vars` (:411) |
| `ebvisu.py` | **leer (0 Byte), getrackt, unbenutzt** |

### Konstanten/Hilfen (Auswahl)
`APP_VERSION` (:79), Pfade `_CFGDIR/PANELS_FILE/CFG_FILE` (:86-91), `_atomic_write` (:153), `VALID_TABS` (:188), `DEVICE_MODELS` (:195),
`_is_tab/_FREE_TAB/_MULTI_TAB` (:449-472; Tab-IDs `favoriten|zentral|raeume|kategorien|free:x|raeume:x|room:<uuid>|cat:<uuid>`),
`STAT_*` (:488-506, Statistik), `MS_*` (:512-520, Retry/Offline), `SAVER_SIZES` (:660), `GRID_SIZES` (:683), `SAVER_WIDE_SIZES` (:693),
`THEME_UI_KEYS` (:907), `BIG_TYPES` (:607), `AMBIENT_*` (:897), `NEULADEN_STUNDE=3` (:896), `_ADMIN_*` (:10893).

### Klasse `App` (:1483-8678, ~7 200 Z.) – Zuständigkeiten
| Bereich | Methoden (Zeile) |
|---|---|
| Init/Zustand | `__init__` (1484: controls/rooms/cats/states, `conn_*`-Dicts je WebSocket, `_last_sent`, Caches), `housekeeping` (1751), `drop_conn` (1667) |
| Miniserver-Verbindung | `start` (1912), `reconnect` (1941), `_connect_ws` (1994), `_renew_token` (2010), `_ms_http/_ms_jdev` (2029/2048), `stream_task` (8049), `_apply_structure/_adopt_structure/_refresh_structure` (1795/1887/1899), `ms_ok` (8207) |
| Werte-Eingang | `_on_value` (7920), `_on_weather` (8000), `push_record/push_uuid` (7980/7990), `_state/_text/_json_state` (2086-2095) |
| Befehle | `command` (7823), `_secured_command` (7893) – Whitelist `_UUID_CMD_RE/_CMD_OK_RE` (:10118) |
| Profil/Theme | `resolve_profile` (2671), `_theme_vars` (2591), `_resolve_ids` (2564), `_panel_export` (4045), `_sanitize_panels` (4119), `_sanitize_theme_ui` (4617), `_sanitize_devices` (4560), `_write_panels/_write_theme/_write_devices` (4401/4688/4539) |
| Tabs/Layouts/Widgets | `_tab_seed` (3026), `_tab_layout` (3076), `_tab_meta` (3340), `_widgets_data` (2959), `_folder_item` (3010), `saver_data` (2753), `status_data/status_chip` (2923/2810) |
| Ansichten (Server rendert Blöcke!) | `render` (7673) → `_view_tab` (5641) / `_view_group` (5653) / `_view_control` (6200) → `_view_control_body` (6609-7672, ~60 Bausteintypen, `if t == "…"`-Kette) / `_view_sources` (5686) / `_view_links` (7696); Kachel: `_control_item` (5066/5082-5566) |
| Hilfsansichten | Raumregler `_irc*` (2187-2380), Audio `_audio_view/_audio_favs` (6145/2393), Wecker `_alarm_*` (4820-4945), Zentral `_central_view/_central_do` (6399/6458), Lichtszenen `_scene_light*` (6489-6575), Anlagenschema `_view_scheme` (6103) |
| Statistik/Charts | `_stat_load/_stat2_load` (4731/4762), `_stat_blocks/chart_blocks/_stat_spark` (5849/5903/5941) |
| Push-Zyklus | `broadcaster` (8442) → `_broadcast_tick` (8234) → `_push_conn` (8312) pro Panel, `_send_or_drop/_send_all` (8137/8171) |
| Nachtmodus | `_night_now` (3471), `_sun_minutes` (3444), `panel_night` (3380), `panel_sensors` (3393), `night_control_options` (3408), `_opmode_active` (3430) |
| Display/Geräte | `panel_dpms` (3371), `panel_reload` (3495), `device_list` (3515), `display_drivers/_drive_display` (3576/3597), `device_detect` (4416), `effective_scale` (4528), `switch_mode` (3983), `kiosk_restart` (3838), `device_brightness` (3796), `device_touch_sound` (3768), `device_adblog` (3912), `launcher_version` (3889), `fully_install/_fully_apk` (3736/3687), `_nightly_restarts` (8221) |
| Front (Wetter/Kalender) | `front_task` (8575), `_front_payload/_front_wetter/_front_nur_wetter/_front_keep` (8455-8517), `_loxone_weather` (8028) |
| Audio | `audio_events_task` (7706), `_audio_client_for` (7768), `_audio_backend_for` (7803), `prime_favs` (2437), `fetch_cover` (4798) |
| Sicherheitsalarm | `sec_alarm_wanted/msg/alarms_active` (2899-2920) |

Sonstige Klassen: `CamHub` (:10393) – teilt EINE Kameraverbindung pro URL auf alle Betrachter (`subscribe/unsubscribe`, `_run`, `_frames`).

### HTTP-Routen (`main()` W:11097+, Registrierung 11106-11181)
Admin = per Passwort geschützt, wenn gesetzt (`_needs_admin` W:10952; Präfixliste W:10894). `security_mw` (W:10987) prüft Fremd-Origin bei POST/WS.
| Pfad | Handler (Zeile) | Zweck |
|---|---|---|
| `/` | `index` 8695 | Panel (`panel.html`) |
| `/config`, `/settings` | `config_index` 8748, `settings_index` 8869 | Konfig-Seite (`settings.html` = Stub/Redirect) |
| `/i18n.js`, `/fonts/{n}`, `/appicon/{s}.png`, `/manifest.webmanifest` | 8752, 10299, 10061, 10073 | Assets |
| `/install-agent.sh` | 8873 | Linux-Agent-Installer |
| `/api/version`, `/api/update` | 8730, 8711 | laufender Stand, neuere Version in release.cfg? |
| `/api/meta` | 8757 | Räume/Kategorien/Controls/Profile/Theme/Gerätemodelle/Designvorlagen für C |
| `POST /api/panels`, `/api/theme` | 8821, 8846 | Profile bzw. globale Darstellung speichern (+ `{t:'reload'}` an alle Panels) |
| `GET /api/settings`, `/api/msstatus`, `/api/types`, `/api/msio` | 8882, 8959, 8977, 9656 | Einstellungsstand, MS-Status, Typ-Diagnose, MS-Ein-/Ausgang lesen |
| `POST /api/settings/{miniserver,cmdwatch,diag,intercom,night,audiometa,calendar,weather}` | 9008, 9050, 9077, 9182, 9125, 9152, 9384, 9348 | je ein Block in `loxpanel.cfg` |
| `/api/settings/diag/{download,clear}`, `/api/settings/intercom/sound[/delete]`, `GET /api/sound` | 9099, 9110, 9261, 9316, 9334 | Diagnose-Log, Klingelton |
| `/api/agent/announce`, `/api/agents`, `/api/agent/command` | 9478, 9508, 9517 | Linux-Panel-Agent |
| `/api/devices` GET/POST | 9601, 9567 | Geräteliste (Betriebsmodus-Zuordnung, Modell, Skalierung) |
| `/api/device/{switch,name,rename,delete,adblog}` | 9608, 9634, 9678, 9739, 9764 | Geräteaktionen |
| `/api/panel/bg`, `/bg/{pid}` | 9689, 9730 | Dashboard-Hintergrundbild |
| `/api/kiosk/{restart,fully,fully/source,fully/upload,brightness,touchsound}` | 9778-9841 | adb-/Fully-Aktionen |
| `/api/panel/launcher[/version]` | 10203, 10196 | Launcher per adb installieren/prüfen |
| `/api/display` | 9886 | Display an/aus (Loxone nutzbar, nicht Admin) |
| `/api/mode[/{mode}]` | 9545 | Betriebsmodus von Loxone → Profil je Gerät umschalten (`switch`) |
| `/api/reload`, `/api/goto`, `/api/notify` | 9936, 9946, 9967 | Panel neu laden / Seite öffnen / Hinweis (aus Loxone) |
| `/api/testtone`, `/api/testring` | 9990, 10010 | Ton-/Klingeltest |
| `/api/tablayout` | 9749 | wirksame Tab-Belegung für Editor-Vorschau |
| `/icon`, `/loxlib`, `/api/loxicons`, `/cover`, `/mjpeg` | 10325, 10346, 10340, 10380, 10539 | Icons (Miniserver-Proxy), Loxone-Bibliothek, Albumcover, Kamera-MJPEG (`?id=&fps=`) |
| `/ws` | `ws_handler` 10625 | Panel-WebSocket |
| `/api/admin/{status,login,logout,password}` | 11011-11043 | Passwortschutz (Hash in `loxpanel.cfg` `admin`) |

### WebSocket-Protokoll (JSON, Feld `t`)
Verbindung: `/ws?panel=<profilId>&device=<Name>&uid=<DEVICE_UID>&kiosk=tbview|fully` (W:10625). Beim Connect schickt der Server der Reihe nach:
`theme`, `view`(Startroute), `front` (falls geladen), `saver`, `ms`, `cmdwatch`, `diag`, `clock`, ggf. `ring`/`secalarm`.

Server → Panel:
| `t` | Felder | Handler im Panel |
|---|---|---|
| `theme` | `vars{--css}`, `tabs[]`, `tabMeta`, `title`, `lang`, `fill`, `split`, `phone`, `scale`, `wake`, `lite`, `panes`, `dpmsOff`, `reloadHours`, `reloadAt`, `night{dim,wake,on}`, `sensors{prox,auto,min,max,nightCam,darkNight}`, `screensaverCam`, `camCrop`, `motion`, `contrast`, `sceneLight`, `iconAnim`, `saver{items,exit,…}`, `ambBg`, `ambClock`, `bgImg`, `agent`, `missing` | P:4343 |
| `view` | `route`, `title`, `layout:'cells'\|'scheme'`/`items[]`/`blocks[]`, … | P:4420ff |
| `front` | `weather`, `events`, `calName`, ggf. `part:'weather'` (nur Wetter) | P:4390 |
| `saver` / `player` / `energy` / `chart` / `camera` | Live-Daten je Widget/Pane | P:4390-4400 |
| `night` | `on` | `setNight` P:5884 |
| `ring` | `id,on,sound,soundUrl` | Klingel: wake + nav auf Türstation |
| `alarm` | `id,on` | Wecker |
| `secalarm` | Sicherheitsalarm-Vollbild (`secAlarm` P:2438) |
| `notify` | `text,level,secs` | `showNotify` |
| `goto` | `route` | wake + nav |
| `display` | `on` | `screenOn/Off` |
| `reload` / `switch{panel}` | Seite neu laden / Profil live wechseln |
| `scale`, `camcrop`, `clock{now,tz,utcoff,build}`, `pong{at,…}` | Skalierung, Kamera-Ausschnitt, Serverzeit (`build` ≠ → Reload) |
| `ms{ok,since}`, `cmdwatch{on}`, `diag{on}`, `cmdack{id,ok}`, `cmdresult{ok}` | Status/Monitoring |
| `setdevice{name}` / `forget` | Gerät benannt / in Config gelöscht |
| `testtone` | Ton testen |

Panel → Server (`ws_handler`, Schleife W:10744ff): `nav{route}`, `cmd{uuid,cmd[,pin][,id]}` (serielle Queue je Panel), `ping{at}`, `devinfo{info}`, `clog{msg}`, `idle`, `setplayer{zone}`, `setenergy{uuid}`, `setchart{uuid,range}`, `setcamera{uuid}`.
Routen (`route`): `{view:'tab',tab}`, `{view:'group',…}`, `{view:'control',id[,range,chart,entry]}`, `{view:'sources',id}`, `{view:'links',id}`.

### Konfigurationsdateien (`config/`-Volume)
- **loxpanel.cfg** (JSON, `_load_cfg` W:143 / `_write_cfg` W:182): `miniserver{host,user,pass,port,verify_tls,msno}`, `intercom{<uuid|cam_x>:{url,user,pass,sound,…}}`, `audio{host,port}`, `audiometa{host,port,enabled,…}`, `night{control}` (`<uuid>` oder `opmode:<Id>`), `calendar{sources[],holiday_url,name,colors,sv_events,lat,lon,days,fore_days,weather_ms,…}`, `cmdwatch{on}`, `diag{on}`, `fully{url}`, `admin{hash}`. (Beispieldatei enthält tote Blöcke `loxone/mqtt/web/lms`.) Umgebung: `LOXPANEL_MS_HOST/USER/PASS/PORT/VERIFY_TLS`, `LOXPANEL_PORT`.
- **panels.json**: `panels{<id>:Profil}` + `devices{<Gerät>:{auto,modes{Modus→Profil},display,model,fully,nrestart,scale}}`.
  Profil: `title`, `tabs[≤4]`, `rooms[]`, `cats[]`, `roomCats`, `hide[]`, `favorites[]`, `alarmPop{uuid:bool}`, `alarmTone`, `tileOrder{scope:[uuid]}`, `saver{items[],exit[]}` (Dashboard), `layouts{tab:{…}}`, `tabIcons`, `tiles{uuid:{iconColor,textColor,bg,border,font,bold,italic,icon,big,chart,chartStyle}}`, `states{active,good,warn,crit}`, `ui{…}`.
- **theme.json**: `states`, `categories{uuid:farbe}`, `ui` (nur `THEME_UI_KEYS`: iconSize, nameSize, subSize, saverFcSize, tileShadow, font, fontNum, textColor, baseColor, design, bold, lang, alarmsEnabled, motion, contrast, sceneLight, dblTapOff, iconAnim, bigValues). Fehlt die Datei → `theme.example.json`.
- **visu.json**: von keinem Code gelesen (nur `visu.example.json`/`visu.schema.json`, Altlast). Ebenso unbenutzt: `ebvisu.py`.
- Weitere: `devinfo.json` (uid→Name/Steckbrief), `scene_light.json` (gelernte Lichtszenen), `pushlog.json`, `diag.log`.

### Profil-UI-Schlüssel `ui.*` (Sanitizing: `_sanitize_panels` W:4119, ui-Teil ab ~4194; global `_sanitize_theme_ui` W:4617)
Nur im Profil (nicht global): `cols`(2|3), `rows`(2|3), `fill`, `split`(false), `phone`, `grid`(2), `nudgeX`(±40), `dpmsOff`(0-3600 s), `reloadHours`(0-168), `nightDim`(0-90 %), `nightWake`(0-300 s),
`prox`(open|off; Standard wake wird nicht gespeichert), `autoBright`(false), `brightMin/Max`(1-100), `nightCam`(false), `darkNight`(true), `player`, `panes{tab:…}` (Altbestand, s. Fallstricke), `ambBg`(light|temp|image), `ambClock`(light|temp).
Profil-Override ODER global: `iconSize/nameSize/subSize/saverFcSize` (8-80, saverFc ≤32), `tileShadow`, `font`, `fontNum`, `textColor`, `baseColor`, `design`, `bold`, `lang`, `motion`(off|mid|full), `contrast`, `sceneLight`, `iconAnim`, `bigValues`.
Konvention: nur Abweichung vom Standard speichern (Standard-Werte werden verworfen).
Auflösung: `ui = {**theme.ui, **profil.ui}` in `resolve_profile` (W:2671), `panel_night/dpms/sensors/reload`. `lang` kommt NUR aus theme.

### Gerätemodelle, Erkennung
- `DEVICE_MODELS` (W:195): `shelly-x2`, `shelly-x1`, `nspro86`, `nspro120`, `sm41-android`, `sm41-debian`, `sm55`, `tablet`, `ipad`, `phone`, `other`; Felder `label, os(android|linux|browser), scale(off|auto), panes, wake, shelly, tips`.
- Erkennung: Panel schickt `devinfo` (P `deviceInfo` :4177: UA, Bildschirm, Fully-/TbView-Steckbrief) → `device_detect` (W:4416) / `guess_device_model` (W:351) / `device_auto_name` (W:383); uid→Name in `devinfo.json`. UID: `tb-<ANDROID_ID>`, `fk-…`, sonst `lp-<random>` (P:4163).
- Typ in Geräteliste: `agent` > `tbview` > `fully` > `browser` (`device_list` W:3515); `caps` (kioskrestart/fullyinstall/brightness/reboot) nur Android.

### Nachtmodus
Ausloeser (`_night_now` W:3471): `night.control` = `opmode:<Id>` (Betriebsmodus) oder Baustein-`active`; sonst Sonnenzeiten (Miniserver-globalStates vor Wetterdienst), sonst `NIGHT_FROM/TO`. Wechsel → `{t:'night'}` im `_broadcast_tick` (W:8299). Stärke je Panel im `theme` (`night{dim,wake}`), Panel dunkelt per Overlay/Fensterhelligkeit (P:5858-5900). Zusätzlich Panel-lokal: `darkNight` (Lichtstufe), `nightCam` (Kamera nur bei Annäherung).

### Wetter / Kalender
`front_task` (W:8575) holt alle `FRONT_INTERVAL`=900 s Kalender+Open-Meteo (`front_info.load_front`), Wetter bevorzugt vom Miniserver (`_loxone_weather` W:8028, Push via `_on_weather`); Ausgabe `{t:'front'}`; Cache `_front`, Delta-Push nur Wetter (W:8287). Lat/Lon notfalls vom Miniserver (`ms_lat/ms_lon`, W:8591).

### Kameras / MJPEG
Config: `loxpanel.cfg intercom`. `mjpeg_handler` (W:10539) → `CamHub` (W:10393), `?fps=` begrenzt je Betrachter (Widget `WIDGET_CAM_FPS`=5). `camera_list` (W:2943), `cam_crops` (W:2890), `_cam_reconnect_h` (W:3133). Panel: `camStream` (P:5290) mit Reconnect-Intervall, `camNightGate/camNightOpen` (P:5366/5373) Nachtsperre.

### adb / Kiosk
`_adb` (W:10158) mit `HOME=config/adb`. `api_panel_launcher` (W:10203): connect → get-state → dumpsys-Version → `install -r` APK → appops (`GET_USAGE_STATS`, `WRITE_SETTINGS`) → Fully ermitteln/Home setzen → URL eintragen. Weitere: `kiosk_restart`, `device_brightness`, `device_touch_sound`, `device_adblog`, `fully_install`, `_nightly_restarts` (3:05, Android+Fully, `nrestart`). Display-Treiber ohne adb: `DISPLAY_DRIVERS` {fully:2323, wallpanel:2971} (W:191).

### Update-Mechanismus
LoxBerry-Auto-Update liest `release.cfg` (GitHub `main`); bei neuerer VERSION lädt es `main.zip`, preroot/postroot sichern/restaurieren Config, `loxpanel-ctl.sh start` baut das Image neu. `/api/update` (W:8711) vergleicht `APP_VERSION` mit `release.cfg` (5 min Cache) nur für den Hinweis in C. `/api/version` zeigt Version + Commit (`bin/version.json`). Panels laden bei geändertem `clock.build` (W:428, `_code_build` W:415) selbst neu.

## 3. Panel `panel.html` (5 985 Z., eine Datei, kein Build)

Aufbau: Zeile 1-21 Kopf/Manifest-Link · `<style>` 22-1976 · `<body>` 1978-2013 · `<script>` 2014-5983.
CSS-Abschnitte (Auswahl): Variablen/Bewegung 35-84, Screensaver-Raster 718, Wetter&Kalender-Ansicht 1045, Layout-Redesign/Tabs 1164, Status-Widget 1427, Alarm-Vollbild 1522, animierte Symbole 1586, Handy 1627, Detail-Listenzeilen 1708, Raumregler 1745, Handy quer `html.pls` 1878, Werte gross 1945.
Body: `#conn`, `#playerpane`, `#frontpane` (Split-Pane), `#grid` (Hauptinhalt), `#scrollInd`, `#tabs`, `#saver` (Dashboard/Schoner: `#svGrid`,`#svBar`,`#svWx`,`#svTime`…), `#frontPage`.

### Zustände
- `ws`, `stack=[{view,tab…}]` (Navigationspfad, P:2072), `view` (zuletzt empfangene Server-Ansicht), `tabsCfg/tabMeta`, `booted`, `frontData`, `saverData/saverCfg`, `NIGHT`, `SENS`, `DISP`, `lpHost`, `DEVICE_ID/DEVICE_UID/PANEL_ID`.
- Navigation: `nav(route)` (2344: push + `send({t:'nav'})` + Zoom-Animation), `back()` (2473), `goTab` (2404), `crumb*` (2413-2432). Server rendert JEDE Ansicht; Panel malt nur: `onWsMessage` (P:4335) → `view.layout`: `scheme`→`renderScheme` (3921), `blocks`→`renderPanel`/`updatePanel` (3155/3329, Detailansicht), `cells`→`render`+`renderCells` (3814/3867, Tab-Raster), sonst `render` + `updateGrid` (3577, Patchen ohne Neuaufbau).

### Wichtigste Funktionen (Zeile)
| Bereich | Funktionen |
|---|---|
| Kommunikation | `send` 2274, `sendWatched`/`cmdAck` 2284/2293 (Befehls-Monitoring), `sendCmd` 2529, `connect` 4306, `wsCheck/wsRestart/linkBanner` 4272/4266/4297 |
| Tabs/Räume/Kategorien | `renderTabs` 3380, `applyPane` 3464, `paneForTab` 3462, `scrollToCat` 3454; Kategorie-Filter/Reihenfolge serverseitig (`_view_tab`) |
| Kacheln | `tileHtml` 3675, `bindTile` 3735, `tileTone` 3521, `blindIcon/windowIcon` 3531/3564, `bigValHtml/fitBigVals` 3660/3665 |
| Detailansichten (Blöcke `b.k`) | `renderPanel` 3155 (Arten: head, hero, value, big, state, slider, dim, shade, scenes, row, status, chips/ist/setp/tline, cover/audiomid/favs, alarmlist/alarmedit, chart, eflow, kpis, log, video, web, more, dhead, title), Helfer `bindLive` 2573, `patchLive` 2678, `bindDhead` 2820, `bindRegler` 2853, `bindAlarmEdit` 2647, `paintChart` 2944, `sparkSvg` 3060 |
| Dashboard/Schoner | `showSaver/hideSaver` 5749/5767, `renderSaverGrid` 4825, `renderLayout` 4883, `svWidgetHTML` 4669 (Widgets clock, weather, calendar, intercom, tile, wxdetail, energy, chart, player, camera, status), `svLive/svPaintLive` 4745/4753, `tickClock` 4457, `ambientApply` 4515 (Farbverlauf) |
| Front (Wetter/Kalender) | `renderFront` 4607, `wxSheet` 5074, `renderFrontRich` 5505 |
| Split-Pane | `applyPane` 3464 (Pane rechts: weather/calendar/wide/player/energy/camera/chart), `renderPlayer` 5787, `renderEnergyPane` 5643, `renderCameraPane` 5654, `renderChartPane` 3036 |
| Popups/Sheets | `sheetFit/sheetSwipe/lpToast/closeSheets` 2303-2334, `openMenu` 2880, `askPin/doSecure` 2497/2526, `stSheet` 5151, `showNotify` 5779, `secAlarm` 2438 |
| Nachtmodus | `NIGHT` 5864, `applyNight` 5875, `setNight/nightEval` 5884/5885, `nightWake` 5895 |
| Display/dpms | `DISP` 5908, `kiosk()` 5910, `applySensors` 5913, `screenOff/On` 5927/5928, `armDpms` 5941, `applyDisplayCfg` 5950, `neuladenFaellig` 5965, `wake` 5977 |
| Host-Brücke | `lpHost` 4141 (Typ tbview→fully→browser; `on(ev,fn)`, `_ev`), `deviceInfo` 4177 |
| Kamera | `camStream` 5290, `camStop` 5317, `camsRefresh/Apply/Dark` 5326-5340, `camStills` 5352, `camNightGate/Update/Open` 5366-5373, `renderScreensaverCam` 5385 |
| Diagnose | `clog` 4247 (Puffer + `clogFlush` 4262, nur wenn `DIAG`), Server loggt `clog` bei Diagnose an |
| Zeit | `setServerClock/nowDate` 4199/4212 (Serverzeit statt Geräteuhr) |
| Skalierung | `scaleCfg/applyScale` 3997/4000 (`--ui-scale`, Rastergröße 480) |
| Icons/Audio | `ICONS` 2015, `LOX_ICONS/loadLoxIcons` 2747/2768, Weckton `toneOn/Off` 2214/2215, `playRingAudio` 2224 |

i18n: das Panel lädt `i18n.js` NICHT (nur Admin-UI `config.html`/`settings.html`, Sprachen de/en). Panel-Texte sind deutsch im Quelltext; `LANG` (aus `theme.lang`, W: `SUPPORTED_LANGS` de/en/fr/it/es/nl) steuert nur Datum/Uhr (`fmtCached` 4224). `data-i18n`-Attribute im Panel (P:5351, 5442, 5501) sind wirkungslos.

## 4. Config `config.html` (5 172 Z.)

Lädt `/i18n.js` (`T('…')`, `I18N.autoChrome`). Start: `load()` (C:1796) → `/api/meta` → `PANELS` (inkl. Pseudo-Profil `__global__` = theme.json) → `setRubric('overview')`.
Rubriken (`setRubric` C:2050): `overview` (`renderOverview` 1880), `pconf` (Profil-Editor `renderEditor` 2406; Unter-Tabs `PCONF_TABS` Profil/Tabs/Aussehen), `global` (Darstellung aller Panels `renderGlobalEditor` 2313, Kategorie-Farben `renderCatColors` 2355), `settings` (System; `SET_TABS` 1790: miniserver, calendar, intercom=Kameras, audio, behavior, security, diagnose), `devices` (`DEV_TABS`: panels=Meine Geräte, newpanel, supported). Navigation `goTo(r,sub)` 2105, `setSub/getSub` 2083, Hash-Direktlink `#devices:newpanel`.
Suche/Palette: `Strg+K` (`openPalette` 2024), `Strg+S` speichert.

### Speichermodell
- Profile/Darstellung: Arbeitskopie `PANELS`; jede Änderung → `markDirty()` (3461) → Speicherleiste; `save()` (3518) POSTet `{panels}` an `/api/panels` und (falls `__global__`) `{ui,categories}` an `/api/theme`; Server schickt `reload` an alle Panels. Snapshot `snapSaved/panelChanges/changeList` (3465-3489, Texte in `CHG_UI`), Undo `undoable/snack` (3497/3507).
- System-/Geräte-Abschnitte: eigene Speicherknöpfe, registriert in `SECTS` (C:2116: ms, wx, cw, ic, dev, fs, am, cal, nt, dg); `sectBind` (2129) markiert Abschnitte per input/change als `SECT_DIRTY`; `sectSaveAll` (2139) ruft deren `onclick`. Gemeinsames „Speichern“ erledigt beides (`save` zuerst `sectSaveAll`).
- Generische Bindung: `bindAppearance` (2204) – `input[data-ui]` (Zahl), `[data-uitext]`, `[data-uichk]` (+`data-def="1"` = Standard an), `select[data-uisel]`; leer/Standard ⇒ Schlüssel wird gelöscht.

### Tab-/Dashboard-Editor
`renderTabEditor` (3022), Bibliothek `tbLibHTML/tbBindLib` (3090/3145), Seitenleiste `tbSideHTML/tbBindSide` (3158/3255), Drag `tbBindDrag` (3330), Raster-Logik `gridSizes/gridDef/gridMin/gridReflow` (2616-2641), `tbPlace/tbFree/tbRows` (2700-2720), `tbCommit` (2748), Laden/Vorbelegen `tbLoad` (2740, `/api/tablayout`), Tab-Eigenschaften `renderTabProps` (2944), Dashboard-Eigenschaften `renderDashProps` (2843; Statusleiste, Hintergrund, Ausstiege), Dashboard-Raster `SV_W` (2586) / `svGrid` (2642). Typen-Liste `TB_TYPES` (2652: free, room, cat, zentral…). Kachel-Editor: `renderTileEditor` (3600), Symbolwahl `renderIconPick/paintLoxone/paintLoxlib` (3678-3742).

### Geräteseite
`renderDeviceList/deviceRow/devRow` (4571/4474/4836), `pollDevices` (4815, alle paar s `/api/devices`), `deviceAction` (4649: `/api/device/*`, `/api/kiosk/*`, `/api/panel/launcher`), `devExtraHTML` (4508), `renderDevices` (4990), Zuordnung Modus→Profil (`readDevFromDom` 4972, `/api/devices` POST), Anzeige/Treiber `displayRow` (4959).

### Assistenten
- Panel-Assistent `pw*` (`pwOpen` 3774 … `pwNext` 3895; Flow `PW_FLOW` start/groesse/tabs/dashboard/design/name/geraet).
- Modus-Zuordnung `mz*` (4696-4799; `MZ_FLOW` geraete/modi/zuordnung/fertig).
- „Gerät hinzufügen“ `np*` (5125ff), `genKioskUrl/genPanelCmd` (5101/5111).
- Weitere System-Karten: Kameras `renderCams` (4219), Kalender `renderCals` (4296), Diagnose `dgLoad` (4384), Admin-Passwort `renderAdminCard` (1971).

## 5. Querschnitt

### Beispiel nightDim (Profil-Einstellung → Panel)
1. C: Eingabe `data-ui="nightDim"` (C:2468) → `bindAppearance` (C:2206) setzt `PANELS[cur].ui.nightDim` → `markDirty`.
2. `save()` → `POST /api/panels` → `_sanitize_panels` klemmt 0-90 (W:4210) → `_write_panels` (W:4401) → `panels.json`; `{t:'reload'}` an alle Panels.
3. Panel lädt, `ws_handler` (W:10625): `resolve_profile` → `panel_night(pid)` (W:3380) merged `theme.ui` + `profil.ui` → in `theme`-Nachricht `night:{dim,wake,on}` (W:10673).
4. P: `onWsMessage` `theme` (P:4372) setzt `NIGHT.dim/wake`, `setNight(on)` → `nightEval` → `applyNight` (P:5875): TbView `setDisplayBrightness(100-dim)` oder schwarzes Overlay `#nightdim`.
5. Tag/Nacht-Wechsel später nur als `{t:'night',on}` aus `_broadcast_tick`; Auslöser stammt aus `loxpanel.cfg night.control` (C: Sektion `nt` → `/api/settings/night`).

### Beispiel sensors (prox, autoBright, brightMin/Max, nightCam, darkNight)
C: Karte „Display & Nacht → Sensoren“ (C:2476-2488, `data-ui`/`data-uisel`/`data-uichk`) → `ui.*` in `panels.json` (Sanitizing W:4212-4221) → `panel_sensors` (W:3393) → `theme.sensors` (W:10674) → P `applySensors` (P:5913): `SENS`-Zustand, `nightEval()`, bei TbView `setProximityWake(…)`, `setAutoBrightness(auto,min,max)`. Rückrichtung: App → `lpHost._ev('prox'|'light'|'screen')` → Handler P:5910-5912 (`nightWake`, `wake`, `camNightOpen`, `camsDark`).

### Wo man bei einer NEUEN Profil-Einstellung überall anfassen muss
1. C: Feld in `renderEditor` + Bindung (`bindAppearance` oder eigener Handler) + ggf. `CHG_UI` (Änderungsliste).
2. W: `_sanitize_panels` (und `_sanitize_theme_ui` + `THEME_UI_KEYS`, falls global möglich), `resolve_profile`/`panel_*`, `theme`-Nachricht in `ws_handler`, ggf. `_panel_export` (:4045, Key-Liste ~4056!).
3. P: `onWsMessage` `theme`-Zweig auswerten.

### Fallstricke
- **P: const/let-Reihenfolge (TDZ):** `NIGHT` (5864), `SENS` (5912), `DISP` (5908), `lpHost` (4141) stehen weit unten/mittig; Top-Level-Code, der sie nutzt, muss danach laufen. Deshalb stehen `setInterval`, `showSaver()`, `resetIdle()`, `connect()` ganz am Ende (P:5966-5970). `lpHost` ist `const` → für die App `window.lpHost=lpHost` (P:4149).
- **Widget-Größenlisten in drei Stellen:** `SAVER_SIZES`/`GRID_SIZES`/`SAVER_WIDE_SIZES` (W:660-695) ↔ `SV_W` (C:2586), `SIZES2` (C:2610), `DASH_WIDE` (C:2615). Neue Widgettypen/Größen immer in beiden Dateien ergänzen (Server verwirft unbekannte Größen in `_widget_entry` W:724). `BIG_TYPES` ebenfalls doppelt (W:607 ↔ C:3580).
- **Neuer Widgettyp** zusätzlich: `SAVER_UUID_TYPES` (W:674), `_widgets_data/saver_data` (W:2959/2753), `svWidgetHTML` (P:4669), ggf. `renderLayout`.
- **Server rendert Blöcke:** Neuer Bausteintyp = `_view_control_body` (W:6609ff) + ggf. Block-Art in `renderPanel` (P:3155); neue Block-Art braucht auch `updatePanel`/`patchLive`-Pfad (sonst kein Live-Update).
- **Sanitizing:** Alles, was nicht im Sanitizer steht, wird still verworfen (`_panels_verworfen` W:4314 meldet nur einen Teil). Standardwerte werden nicht gespeichert.
- **Reload-Kaskade:** Speichern in C → `reload` an ALLE Panels. `clock.build` (Code-Stempel) lässt Panels nach Server-Update ebenfalls neu laden.
- **Versionsstellen beim Release (CLAUDE.md):** `plugin.cfg` VERSION, `release.cfg` VERSION, `APP_VERSION` (W:79), Changelog-Eintrag oben in `README.md`; `python3 -m py_compile config/app/bin/webvisu.py`; Launcher-Änderung: `AndroidManifest.xml` versionCode/Name + neu bauen (`.version`-Datei). Nicht ändern: `NAME/FOLDER` in `plugin.cfg`.
- **Umlaute:** Kommentare ohne Umlaute, UI-Texte mit Umlauten über `T('…')`; Schlüssel der Übersetzung = deutscher Text (`i18n.js`), ändert man den Text, geht die en-Übersetzung verloren.
- **Zeilenverweise in `docs/TBVIEW.md`** (~4127, ~4146, ~4271, ~5803) sind veraltet; richtig: siehe Tabellen oben.
- **Lokal testen:** nie auf 8097 (echte Anlage) schalten/speichern; Testserver `lpdev` auf 8099.
