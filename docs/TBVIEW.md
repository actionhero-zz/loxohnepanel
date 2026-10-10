# TbView – eigene Kiosk-App statt Fully (Stand 2026-10-10)

Ziel: Ersatz für Fully Kiosk. Fully bleibt Fallback. Vorbild ist `LoxKiosk` aus
Lenardo1/Loxpanel (`android/app/src/main/java/com/loxpanel/spike/KioskActivity.kt`,
`Helligkeit.kt`). LoxKiosk wird **nicht** als eigener Typ unterstützt (keine
Config, keine Erkennung) – nur Code-Teile werden übernommen (Lizenz/Notice beachten).

## Basis
- Eigener Launcher `android/panel-launcher` (Java, `build.sh`, `launcher.keystore`,
  ohne Gradle) bekommt eine Kiosk-Activity mit WebView. Original ist Kotlin+Gradle+
  Chaquopy (Server läuft dort auf dem Gerät) – das brauchen wir nicht.
- Bereich der Cloud-Instanz (adb/Android), Panel-Seite lokal.

## JS-Brücke `window.TbView`
Namen wie Fully/LoxKiosk, damit das Panel alle gleich behandelt:

| Methode | Wirkung |
|---|---|
| `turnScreenOn()` / `turnScreenOff()` / `isScreenOn()` | Schoner weg/an (schwarzes Overlay + Helligkeit 0) |
| `setDisplayOff(sek)` | Backlight aus n s nach Start des Panel-Schoners, 0 = nie |
| `setSaver(on)` | Panel meldet eigenen Schoner (Uhr); App dunkelt danach selbst |
| `setDisplayBrightness(prozent)` | Fensterhelligkeit in % der Systemhelligkeit; `false` bei Auto-Helligkeit -> Panel dunkelt per Overlay |
| neu: `getDeviceId()`, `getDeviceInfo()` | stabile ID/Steckbrief (Ersatz für Fully-Steckbrief) |
| neu: Ereignis Näherung | App ruft `window.lpHost.onProximity(nah)` |

## Näherungssensor (übernehmen)
- Shelly: Wake-up-Sensor, `getDefaultSensor()` liefert ihn nicht ->
  `getSensorList(TYPE_PROXIMITY).firstOrNull() ?: getDefaultSensor(...)`.
- In `onResume` mit `SENSOR_DELAY_FASTEST` registrieren, in `onPause` abmelden.
- `nah = values[0] < maximumRange`. Nah im Schoner -> aufwecken + `wake()` im Panel.
- Befund 0.1: Sensor (`/dev/input/event5`, ABS_DISTANCE 0/1) sendet nur, wenn eine App
  ihn anmeldet -> genau das macht TbView. Firmware-Weckung greift nur beim
  Hersteller-Launcher.
- Zusätzlich an das Panel melden (Roadmap 0.5: Kamera live nur bei Näherung).

## Helligkeit (übernehmen)
- Nur Fenster: `window.attributes.screenBrightness`; Geräteeinstellung bleibt.
- Systemhelligkeit lesen (`Settings.System.SCREEN_BRIGHTNESS`, ohne Berechtigung),
  Max aus `config_screenBrightnessSettingMaximum` (AOSP 255, manche 2047).
- Auto-Helligkeit -> Wert unbekannt -> `false`.
- Nachtmodus: 70 % abdunkeln = 7 % der Systemhelligkeit (gleiche Leuchtdichte wie Overlay).
- `FLAG_KEEP_SCREEN_ON`, damit der Sensor aktiv bleibt; Schoner = eigenes Overlay.

## Panel / Server
- `lpHost` in `panel.html`: Erkennung `TbView` -> `fully` -> Browser (kein LoxKiosk).
  Stellen: Geräte-ID (`fk-` Fully, `tb-` TbView), Steckbrief `deviceInfo`, `kiosk=`-Meldung,
  Kamera `isScreenOn`, `kiosk()` (Zeilen siehe docs/ARCHITEKTUR.md).
- `webvisu.py`: `kiosk=tbview` annehmen, Typ in Geräteliste.

## ShellyElevate (RapierXbox/ShellyElevate) – bessere Vorlage
Java, Apache-2.0 (Code übernehmbar mit Notice), aktiv gepflegt, alle Shelly-Displays inkl. X2i (Jenna).
Kiosk-WebView als Fully-Ersatz, Lite-Modus neben Fully möglich. Gefunden über rtho782/shelly-x2i-root.
- **Näherung X2i:** nicht zuverlässig über SensorManager (LoxKiosk-Weg!). Drei Wege nacheinander:
  1. `SensorManager TYPE_PROXIMITY`, 2. JNI `libshellyinput.so` liest `/dev/input/event*`
  (`KEY_F5` nah / `KEY_F6` fern), 3. Fallback `getevent -l` parsen. Unser Befund 0.1
  (event5 ABS_DISTANCE, kein F5/F6 gesehen) passt nur teilweise -> alle Wege einbauen.
- **Helligkeit:** sysfs-Backlight (`/sys/devices/platform/leds-mt65xx/leds/lcd-backlight/brightness` u. a.),
  Auto-Helligkeit aus Lux (<30 lx -> min 48, >500 lx -> 255, 3 s Hysterese, Animation 50 ms).
- **JS-Brücke `ShellyElevate`:** `getLux/getProximity/getTemperature/getHumidity`, `get/setScreenBrightness`,
  `sleep/wake`, `keepScreenAlive`, `getRelay/setRelay`, Ereignisse per `bind()` (`onMotion`, `onScreenOn/Off`,
  `onButtonPressed`) – nur mit „Extended JavaScript Interface“.
- Zusätzlich HTTP-API :8080, MQTT, Relais, Taster, Temperatur/Feuchte.

## Code-Befund ShellyElevate (Stand 0043c23) und Folgen für TbView
- Jenna (`DeviceModel.java:28-35`): Näherung `invertProximity`, Eingabegeräte `/dev/input/event4,5,7`
  (dort: event4 = gpio_keys KEY_F5/F6). Unser Log 0.1: event4 = lightsensor-level, event5 = proximity
  (ABS_DISTANCE). -> beide Formate auswerten (EV_KEY 63/64 und EV_ABS ABS_DISTANCE).
- JNI-Lib nur Komfort: `open()` lesend auf `/dev/input/eventN`. Geht auch in reinem Java
  (FileInputStream, `input_event` 24 Byte auf 64 bit / 16 Byte auf 32 bit) -> kein NDK nötig.
  Ob eine normale App das auf dem X2i lesen darf, belegt niemand -> **erst Gerätetest**.
- Helligkeit Jenna: sysfs gesperrt (EACCES); ShellyElevate nutzt `Settings.System.SCREEN_BRIGHTNESS`
  (+ `adb shell appops set <pkg> WRITE_SETTINGS allow`). TbView nimmt die Fensterhelligkeit
  (`screenBrightness`, keine Berechtigung, Geräteeinstellung bleibt) wie LoxKiosk.
- Lux: nur `SensorManager TYPE_LIGHT` (1 s / 15 % gedrosselt). Auto-Kurve <30 lx min, >500 lx max, 3 s Hysterese.
- Installation: normale App per `adb install -g`, kein Root.

## Plan TbView (Variante A, auf LoxPanel zugeschnitten)
1. Gerätetest-APK: liest `/dev/input/event4,5,7` + Proximity/Light-Sensor, zeigt Werte an. Klärt Leserecht und Format.
2. Launcher um Kiosk-Activity erweitern: WebView auf Panel-URL, Brücke `TbView`, Schoner (Overlay + Helligkeit 0),
   Wecken per Berührung/Näherung, Fensterhelligkeit + Auto-Helligkeit (Lux) + Nachtfaktor.
   Modus im Launcher: TbView oder Fully (Fallback).
3. Panel `lpHost` (TbView -> fully -> Browser) inkl. `onProximity`, Server `kiosk=tbview`.
Build auf dem Pi: aapt/apksigner/zipalign (apt) + `~/projekte/tools/android/{d8.jar,android.jar}`.

## Gerätetest X2i (192.168.1.247, 2026-10-10, Test-App ~/projekte/tools/tbtest)
- SELinux permissive, `/dev/input/event0-6` für alle lesbar -> normale App liest event4/5 ohne Root.
- Näherung über `SensorManager` funktioniert (auch `getDefaultSensor`, Wake-up, max 1.0):
  `0.0` = nah, `1.0` = fern. 15 Wechsel sauber erkannt. -> **SensorManager reicht**.
  `event5` (ABS_DISTANCE, code 25) liefert parallel invertiert: `1` = nah, `0` = fern. Nur Reserve.
  Kein KEY_F5/F6 auf diesem Gerät (ShellyElevate-Angabe gilt hier nicht).
- Licht: `TYPE_LIGHT` liefert **Stufen 0–16**, keine echten Lux (gleich `event4`, ABS_MISC code 40).
  -> eigene Kurve Stufe -> Helligkeit, ShellyElevates 30/500-lx-Schwellen passen nicht.
- Build-Kette auf dem Pi: javac 21 (-source/-target 8) + **r8 8.5.35** (`tools/android/r8.jar`);
  d8 aus build-tools 33/34 stürzt bei anonymen Klassen ab.

## Stand Launcher 5.0 (2026-10-10, getestet auf X2i)
- `Kiosk.java`: WebView (Hardware-Layer, kein Zoom/Long-Press, Safe Browsing aus, Renderer-Prio hoch,
  Renderer-Absturz -> neu aufbauen, Offline-Seite mit Neuversuch alle 3 s), Brücke `TbView`.
- Getestet: lädt Panel (~84 MB PSS), `turnScreenOff/On`, `isScreenOn`, Helligkeit, Wecken per
  Näherung (21 s Test), `lpHost` im Panel (`type=tbview`), Nachtmodus über echte Helligkeit,
  Server erkennt `kiosk=tbview` und Modell `shelly-x2` (Codename Jenna).
- Umschalten: `adb shell am start -n de.loxpanel.launcher/.Main --es mode tbview|fully [--es url …]`.
  Config bietet nur „TbViewer installieren“ (Fully nur noch Fallback per adb, nicht in der Oberfläche).
- Geräte-ID unter TbView: `tb-<ANDROID_ID>` (Fully: `fk-…`) -> Gerät erscheint beim Wechsel neu.
- Lichtsensor meldet erst bei Änderung; bis dahin Systemhelligkeit.
- Offen: Lichtkurve (Stufe -> Helligkeit) am Gerät abstimmen; Kamera live nur bei Näherung (0.5).

## Sensor-Optionen in der Config (Profil -> Aussehen -> Display & Nacht -> Sensoren)
- `ui.prox`: Bei Annäherung `wake` (Standard, Display an) | `open` (Display an + Dashboard schließen) | `off`.
- `ui.autoBright` (false = Systemeinstellung), `ui.brightMin`/`ui.brightMax` in % (Standard 10/100).
- Server -> Panel: `sensors {prox, auto, min, max}`; Panel -> App: `setProximityWake`, `setAutoBrightness(on,min,max)`.
- Nachts wirkt „Abdunkeln um“ zusätzlich auf die Auto-Helligkeit.

## Anwendungsfälle Sensoren (Panel, ab Launcher 5.1)
- **Nachts Kamera nur bei Annäherung** (`ui.nightCam`, Standard an): bei Nacht + TbView mit Näherungssensor
  sind alle Kamerabilder (Dashboard, Schoner, Widget, Türstation; alle über `camStream`) angehalten.
  Sichtbar: abgedunkeltes, unscharfes Standbild + Mond + „Live-Bild bei Annäherung“ (`html.camnight`).
  Live bei Annäherung, Berührung oder Klingel (`wake()`), 30 s Nachlauf nach „fern“.
- **Annäherung hellt nachts kurz auf** (wie Berührung, `nightWake`), außer `prox=off`.
- Tag/Nacht kommt **nur** aus dem Betriebsmodus der Config (Nutzervorgabe), nicht vom Lichtsensor.
- **Dynamische Helligkeit** (`ui.autoBright`, min/max): nur Shelly mit TbView + Lichtsensor regelt nach dem Sensor (ohne „Abdunkeln um“); alle anderen Geräte und Option aus: Abdunkeln nach Betriebsmodus.
- Ereignisse App -> Panel: `window.lpHost._ev(name, wert)`; Fix 5.1: `lpHost` ist `const`, daher
  `window.lpHost=lpHost` im Panel (vor 5.1 kamen keine Ereignisse an).

## Namen (ab 0.20.0)
- App (Launcher + Kiosk-Ansicht): **TbViewer**; sie zeigt die Web-App **tilebert** an.
- Technisch bleiben: JS-Brücke `window.TbView`, `kiosk=tbview`, Geräte-ID `tb-`, Paket `de.loxpanel.launcher`, Datei `LoxPanel-Launcher.apk`.
