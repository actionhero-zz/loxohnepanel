# Loxone-Wissensbasis für LoxPanel (Nachschlagewerk)

Stand: 2026-10-10. Zeilennummern = Arbeitsbaum, driften bei Edits (bei Zweifel `grep -n`). Kürzel: `W` = `config/app/bin/webvisu.py`,
`WS` = `config/app/bin/loxone_ws.py`, `P` = `config/app/webfrontend/html/panel.html`.

## 0. Quellen und Belastbarkeit

| Kürzel | Quelle | Verwendung |
|---|---|---|
| [SF] | Loxone „Structure File“ V17.0 (31.3.2026, 157 S.): https://www.loxone.com/dede/wp-content/uploads/sites/2/2026/04/1700_Structure-File.pdf (ältere Stände u. a. 1701/1200/1100 auf derselben Domain, `.../wp-content/uploads/sites/2/.../xxxx_Structure-File.pdf`) | alle States/Details/Befehle je Control-Typ (Abschnitte B/C) |
| [COM] | Loxone „Communicating with the Miniserver“ V17.0: https://www.loxone.com/dede/wp-content/uploads/sites/2/2026/04/1700_Communicating-with-the-Miniserver-2.pdf | Websocket, Auth, Binärformat (Abschnitt A) |
| [KB] | Loxone Knowledge Base: https://www.loxone.com/dede/kb/lichtsteuerung-v2/ , https://www.loxone.com/enen/kb/irc-v2/ , https://www.loxone.com/dede/kb/systemstatus/ , https://www.loxone.com/dede/kb/url-schema-der-loxone-smart-home-app/ | Verhalten/Begriffe, teils App-Bezug |
| [APP] | https://www.loxone.com/dede/?p=333913 (App-Einrichtung/Navigation) | Startseite Favoriten/Zentral/Räume/Kategorien/Menü |
| [LIVE] | Echte Anlage, nur lesend: `GET http://127.0.0.1:8097/api/types` (Typen/States/Details je Typ, nicht unterstützte Controls, operatingModes, globalStates) und `GET /api/meta` (Räume/Kategorien) | Abschnitt B „Anzahl in Anlage“ |
| [CODE] | LoxPanel-Code (W, WS, P) | Spalte „LoxPanel“ |

**Wichtige Einschränkung:** Loxone dokumentiert *Daten und Befehle* gründlich, aber *wie die App einen Baustein zeichnet* (Kachelaufbau, Farben,
Icons je Zustand) praktisch nicht. Was in „Darstellung in der App“ steht, ist entweder mit [KB]/[APP] belegt oder ausdrücklich als
„(nicht dokumentiert)“ bzw. „(Beobachtung nötig)“ markiert. Für Pixelgenauigkeit hilft nur Vergleich mit der echten App (Screenshots).
Die Online-Hilfe nennt unter `loxone.com/dede/kb/...` je Baustein Verhalten/Parameter; einzelne URLs ändern sich (z. B. lieferten
`/kb/irc-v2/` auf `dede` und `/kb/beschattung/` 404; `enen/kb/irc-v2/` geht).

---

# A) Miniserver-Grundlagen

## A1. Die Strukturdatei `LoxAPP3.json`
- Abruf: `data/LoxAPP3.json` (per Websocket Text-Message oder HTTP). Zeitstempel `lastModified`; beim Verbinden `jdev/sps/LoxAPPversion3`
  vergleichen und nur bei Abweichung neu laden [COM S.22-23].
- Top-Level [SF S.9-14]: `lastModified`, `msInfo`, `globalStates`, `operatingModes`, `rooms`, `cats`, `controls`, `weatherServer`, `times`,
  `caller`, `autopilot`, `mediaServer`, `messageCenter`.
- **msInfo:** `serialNr, msName, projectName, localUrl, remoteUrl, hostname, tempUnit` (0 = °C, 1 = °F, Temperaturen kommen dann in °F!),
  `currency`, `location, latitude, longitude, altitude`, `catTitle, roomTitle` (Gruppen können „Zone“ statt „Raum“ heißen), `miniserverType`,
  **`sortByRating`** (Sortierung nach Sternen 0-5 = `defaultRating`), **`currentUser`** (`name, uuid, isAdmin, changePassword, userRights`).
- **globalStates** (UUIDs, Werte kommen als normale Events): `sunrise` (Sekunden seit Mitternacht), `sunset`, `favColors`, `favColorSequences`,
  **`notifications`** (JSON je Meldung `{uid, ts, type:10, title, message, data:{lvl:1 Info|2 Fehler|3 Systemfehler, uuid?}}`),
  `miniserverTime`, `liveSearch`, `modifications`. In der Anlage zusätzlich (via /api/types): `operatingMode, pastTasks, plannedTasks,
  userSettings(+Ts), hasInternet, cloudservice, propsVersion, trustVersion`.
- **operatingModes:** Map ID → Name. IDs 0-2 = Feiertag/Urlaub/Freier Tag (priorisiert), 3-9 = Mo-So, 10/11 = Heiz-/Kühlperiode, negative IDs
  = benutzerdefinierte Betriebsmodi. Anlage [LIVE]: u. a. `-1 Alarm, -2 Anwesenheitssimulation, -3 Haus im Tiefschlaf, -5 Party, -6 Abwesend,
  -999 Tag, -1000 Schlafen, -1004 Anwesend` und viele Lichtmodi (LM1-LM5, Schlafmodus Eltern/Emmi/Jungs ...). Genutzt von Daytimern,
  IRC, Wecker und (in LoxPanel) für die Nacht-Erkennung (W:3413).
- **rooms:** `uuid, name, image (Icon-UUID), defaultRating`. **cats:** `uuid, name, image, type (lights|indoortemperature|shading|media), color,
  colorShade (ab 17.0), defaultRating`. Anlage [LIVE]: 23 Räume (inkl. „Nicht zugeordnet“, „Spezial“, „Meldezentralen“), 27 Kategorien.
- **Control (Pflicht):** `name, type` (leerer Typ = nicht visualisieren), `uuidAction, defaultRating, isSecured`.
  **Optional:** `room, cat, states{name→uuid}, details, subControls{uuid→control}, statistic / statisticV2, securedDetails, restrictions`
  (Bit0 intern „nur referenziert“, Bit1 intern **read-only**, Bit4/5 dasselbe extern), `hasControlNotes` (Text via
  `jdev/sps/io/<uuid>/controlnotes`), `preset{uuid,name}`, `links[]` (verknüpfte Controls), `isFavorite`, `defaultIcon`.
- **Sperren (ab 11.3.2.11):** `details.jLockable`; State `jLocked` (Text-JSON `{locked:0|1 visu|2 logic, reason}`, leer = nicht gesperrt).
  Gesperrte Controls ignorieren API-Befehle. Admin-Befehle: `lockcontrol/<0|1>/<grund>`, `unlockcontrol` [SF S.16-17].
- **Control History (ab 14.5):** `details.hasHistory:true` → `jdev/sps/io/<uuid>/gethistory` liefert `[{ts, what, trigger, impacts[], triggerType, triggerUuid}]`;
  triggerType: user | control | logic | automaticRule | scene | centralGw | device | generic [SF S.24-25].
- **Statistik:** `statistic` (alt: `frequency`, `outputs[{id,name,format,uuid,visuType 0 Linie|1 digital|2 Balken}]`; Daten
  `statistics.json`, `statisticdata.xml/<uuid>/<YYYYMM[DD]>`, `binstatisticdata/...`) bzw. **`statisticV2`** (Gruppen/dataPoints,
  `jdev/sps/getStatisticInfo/<uuid>`, `getStatistic/<uuid>/raw|diff/<von>/<bis>/<all|hour|day|month|year>/<gruppe>/<output>`; Binär: Uint32 ts + Float64 je Wert).
- **securedDetails:** sensible Daten (z. B. Intercom-Video-URL/User/Pass) nur per eigener, **verschlüsselter** Abfrage `jdev/sps/io/<uuid>/securedDetails`.
- **Icons:** UUID-Dateien `…svg` (neu) oder `…png`/ohne Endung (alt); per Websocket/HTTP über „UUID + Endung“ abrufbar. Bei Status-Icons ist das
  Format unbekannt: erst `.svg` versuchen; kommt eine Text-Message, ist es SVG, sonst PNG. Icon-UUIDs ändern sich nicht (cachebar) [COM S.22].
- **URL-Schema der App** (nützlich für Deep-Links): `loxone://ms?mac=<MAC>&loc=home|weather|favorites|room|category|menu|taskrecorder|room/<uuid>|category/<uuid>|control/<uuid>` [KB].

## A2. Verbinden, Auth, Websocket [COM]
1. Erreichbarkeit/Version: `/jdev/cfg/apiKey` (enthält `httpsStatus`, ab 12.1 `local`).
2. Zertifikat `jdev/sys/getcertificate` → Public Key. Websocket `ws(s)://host:port/ws/rfc6455`, Subprotokoll `remotecontrol`.
3. Sitzungsschlüssel: AES256-CBC-Key+IV, RSA-verschlüsselt per `jdev/sys/keyexchange/<enc>`. Ab 11.2 mit TLS (Gen 2) nicht mehr Pflicht.
4. Token: `jdev/sys/getkey2/<user>` → key/salt/hashAlg; `pwHash = UPPER(hash("<pw>:<userSalt>"))`; `hash = HMAC(key, "<user>:<pwHash>")`;
   `jdev/sys/getjwt/<hash>/<user>/<permission>/<uuid>/<info>` (verschlüsselt!). Permission 2 = Web (kurz), 4 = App (Wochen). Antwort: `token, validUntil
   (Sek. seit 1.1.2009), tokenRights, unsecurePass, key`. Danach `authwithtoken/<hash(token,key)>/<user>`; ab 11.2 Token auch im Klartext. Verlängern
   `jdev/sys/refreshjwt/...`, prüfen `checktoken`, beenden `killtoken`.
5. Rechte-Bits (Auszug): 0x1 Admin, 0x2 Web, 0x4 App, 0x8 Config, 0x40 Expertenmodus, 0x80 Betriebsmodi ändern, 0x200 Automatik-Designer, 0x800 Benutzerverwaltung.
6. **Status abonnieren:** `jdev/sps/enablebinstatusupdate`. Danach großer Initial-Dump aller Events, später nur Änderungen. Max. 31 gleichzeitige
   Event-Clients (`hasEventSlots`); Close-Code 4008 = keine Slots. Nur Controls, die in der Visu verwendet werden, liefern States.
7. **Keepalive:** Client sendet `keepalive` (Miniserver trennt nach > 5 min Stille); Antwort = Header mit Kennung 6.
8. **Fehlercodes:** 401 unautorisiert, 403 Rechte fehlen, 404 unbekannter Befehl, 423 Benutzer gesperrt, 503 Neustart, 901 max. Verbindungen; Close 4003 gesperrt
   (zu viele Fehlversuche), 4004-4006 Benutzer geändert/deaktiviert, 4007 Update.

## A3. Binärformat der Nachrichten [COM S.18-21]
Jede Nachricht = 8-Byte-Header (`0x03`, Kennung, Info-Flags [Bit0 = Länge nur geschätzt, danach kommt ein exakter Header], reserviert, UInt32 LE Länge),
dann die Nutzdaten als eigene Websocket-Nachricht.

| Kennung | Inhalt | Format |
|---|---|---|
| 0 | Text-Message (Antwort auf Befehle, auch LoxAPP3.json) | JSON/Text |
| 1 | Binärdatei (Bild, Statistik) | roh |
| 2 | **Wert-Events** | je 24 Byte: UUID (16) + Double LE |
| 3 | **Text-Events** | UUID (16) + Icon-UUID (16) + UInt32 Länge + Text, auf 4 Byte aufgefüllt |
| 4 | **Daytimer-Events** | UUID, Double Default, Int Anzahl, je Eintrag: Int Modus, von (Min seit 0:00), bis, needActivate, Double Wert |
| 5 | Out-of-Service (Update/Neustart; danach Close) | nur Header |
| 6 | Keepalive-Antwort | nur Header |
| 7 | **Wetter-Events** | UUID, UInt32 lastUpdate (Sek. seit 2009), Int Anzahl; je Eintrag: timestamp, weatherType, windDirection, solarRadiation, relativeHumidity (Int) + temperature, perceivedTemperature, dewPoint, precipitation, windSpeed, barometricPressure (Double) |

UUID-Binär: `Data1` (4 B LE) `Data2` (2 B) `Data3` (2 B) `Data4` (8 B) → String `%08x-%04x-%04x-%02x…` (letzter Block 16 Hex-Zeichen).

**Wertetypen in der Praxis:** *Wert* = Double (digital 0/1, analog Zahl, Position 0..1), *Text* = String (oft JSON, z. B. `moodList`, `zones`, `jLocked`, `entryList`),
*Daytimer* = Ereignistabelle, *Wetter* = Tabelle (Wettertyp-Texte in `weatherServer.weatherTypeTexts`). Sentinels wie 2147483.647 = „kein Wert“.

**LoxPanel (WS):** Kennung 2/3/7 werden gelesen (WS:249-257), 5 und 6 behandelt (WS:231-242), **Kennung 4 (Daytimer) wird nicht geparst**, nur einmal als
„unbekannte Kennung“ geloggt (WS:258-263). Ob `entriesAndDefaultValue` der Anlage trotzdem über Kennung 3 kommt, ist unverifiziert (siehe C-12).

## A4. Befehle (Steuerung)
- Control-Befehl: `jdev/sps/io/<uuidAction>/<befehl>` (Parameter mit `/` getrennt, z. B. `changeTo/3`, `volume/40`). Antwort: Text-Message mit `Code`
  (200 ok) – der Rückgabewert ist **nicht** verlässlich, besser den State-Update abwarten [COM S.14].
- Geschützte Controls (`isSecured: true`): Visu-Passwort: `jdev/sys/getvisusalt/<user>` → `visuPwHash = hashAlg("<pw>:<salt>")`, `hash = HMAC(key, UPPER(visuPwHash))`,
  Befehl `jdev/sps/ios/<hash>/<uuid>/<befehl>`; 200 = ok, 500 = falsches Passwort; Prüfen ohne Wirkung: `jdev/sps/checkuservisupwd/<hash>`.
  LoxPanel: `W:7891` (`_secured_command`), Kachel-Flag `secured` (W:5093).
- Zentralbausteine: `selectedcontrols/<ids,>/<befehl>` (CentralAlarm on/off/quit/delayedon; CentralAudio play/pause/volup/voldown; CentralGate open/close/stop;
  CentralJalousie FullUp/FullDown/shade/auto/NoAuto/stop; CentralLightController on/reset/setMoods; CentralWindow ...). Details.controls = `[{uuid,id}]`.
  LoxPanel löst Zentralbausteine selbst auf (Befehl je Einzelcontrol, `_central_do` W:6458) statt `selectedcontrols`.
- Presets: `…/resettodefaultall/<presetUuid>`. Verknüpfte Controls: `links[]`.

## A5. Darstellung/Struktur in der App (soweit dokumentiert)
- Startseite/Dashboard: **Favoriten** (wichtigste Funktionen), **Zentral** (Gebäudeweites, z. B. Brandmeldezentrale, Energie-Überblick), **Räume**,
  **Kategorien** (Licht, Audio ...); Menü: Einstellungen, Neuigkeiten, Szenen, Automatik-Designer, Task Recorder [APP][KB-URL-Schema].
- Reihenfolge: Sterne (`defaultRating`) nur wenn `msInfo.sortByRating`; Räume/Kategorien/Controls analog.
- Kategorien tragen Farbe (Icon-Farbe), Typ gibt Semantik (lights/indoortemperature/shading/media).
- **Systemstatus** (`messageCenter`): nur sichtbar bei aktiven Meldungen; farbiges Herz + Balken in der Titelleiste; Stufen Info/Warnung/Wichtig/Kritisch;
  Detail mit Ursache + Lösungshinweisen; manche Meldungen nur für Admins [KB systemstatus].
- Push/Benachrichtigungen: auch live über den Websocket (`globalStates.notifications`, nur wenn Benutzer berechtigt/registriert) [SF S.11].
- Texte für Zustände (Statusbausteine): `TextState.textAndIcon` (Text + Icon-UUID im Text-Event), `iconAndColor` (JSON `{icon, color}`, ab 13.1);
  `InfoOnlyDigital.details.text/color/image{on,off,onColor,offColor}`; `InfoOnlyAnalog/Text.details.format` (C-Format).
- Hinweis: Loxone legt je Baustein *keine* verbindliche Kachelgestaltung offen; Kachel = Icon + Name + Statuszeile ist App-Konvention (nicht dokumentiert).

---

# B) Control-Typen

Legende LoxPanel-Status: **voll** = Kachel + Detail + Befehle, **teilw.** = Kachel/Detail da, aber relevante States/Befehle fehlen, **nur Anzeige**,
**fehlt** = keine Kachel-/Detail-Logik (Kachel hat dann keine Navigation = „tote Kachel“; `PARTIAL_TYPES` W:598, Statusermittlung `types_overview` W:4970).
Zeilen: K = Kachel (`_control_item_build`, W:5079-5566), D = Detail (`_view_control_body`, W:6609-7672).

## B0. Überblick der Anlage [LIVE] (318 Controls, 39 Typen: 31 voll, 5 teilw., 3 fehlen)

| Typ | Anz. | LoxPanel | Beispiele |
|---|---:|---|---|
| InfoOnlyAnalog | 80 | voll | Luftfeuchte, Temperatur, Helligkeit |
| Switch | 55 | voll | BWM aus Terrasse, Spots per Schaltuhr |
| LightControllerV2 | 26 | voll (aber ohne Kreise/Farbe, s. u.) | Lichtsteuerung Garagenweg/Terrasse |
| Meter | 21 | voll (reduziert) | E-Heizung Bad, Pool |
| TextState | 20 | voll | Status, Luftqualität |
| InfoOnlyDigital | 18 | voll | Sonnenschein, Türfenster |
| Jalousie | 16 | voll (ohne Position/Lamelle/Auto) | Tür, Essbereich Fenster |
| Pushbutton | 14 | voll | Emmi Szene Nacht, Bewässerung abbrechen |
| Slider | 7 | voll | WW aufheizen Dauer |
| Tracker | 7 | voll | Gartenpumpe, Doorbird Online Status |
| AlarmClock | 7 | teilw. | Wecker, Wecker Bewässerung |
| TimedSwitch | 6 | voll | Beete manuell |
| PresenceDetector | 5 | voll (nur Anzeige) | EG Wohnzimmer, Präsenz Bad |
| Alarm | 3 | voll | Alarmanlage, Außenhüllen-, Regenüberwachung |
| SmokeAlarm | 3 | voll | Brandmelde-, Wassermeldezentrale |
| PulseAt | 3 | **fehlt (tote Kachel)** | Fassadenspot an/aus, Haus geht automatisch schlafen |
| Daytimer | 2 | voll (nur Override) | Schaltuhr, Stoßlüften Timer |
| Radio | 2 | voll | Licht Betriebsmodus, Sonnenschutz Steuerung |
| Intercom | 2 | teilw. | Coodeknacker, Doorbird |
| Irrigation | 2 | teilw. (nur Start/Stopp) | Bewässerung Beete/Rasen |
| AalEmergency | 1 | **fehlt (tote Kachel)** | Panikalarm |
| NfcCodeTouch | 1 | **fehlt (tote Kachel)** | NFC Code Touch |
| AudioZone / AudioZoneV2 | 1 / 1 | teilw. / voll | Zentral |
| CentralAlarm / CentralAudioZone / CentralJalousie / CentralLightController | je 1 | voll | Alarm Zentral, Audio Zentral, Rolläden zentral, Licht Zentral |
| EFM / EnergyManager2 / Fronius | je 1 | voll | Energieflussmonitor, Energiemanager, Energiemonitor |
| Gate | 1 | voll | Tor |
| Hourcounter | 1 | voll (Einheit prüfen!) | Heizung Heizstab mit PV Überschuss |
| IRoomControllerV2 | 1 | voll (reduziert) | OG Bad |
| MailBox | 1 | voll (nur Anzeige) | Briefkasten |
| Ventilation | 1 | teilw. (nur Anzeige) | Raumlüftungssteuerung |
| Webpage | 1 | voll | Cams Eingangsbereich |
| WindowMonitor | 1 | voll | Fenster- und Türüberwachung |

Stand `jLocked`/`jLockable` kommt in **allen** Typen der Anlage vor (States/Details); `hasHistory` bei Jalousie, LightControllerV2, IRoomControllerV2, Gate.

## B1. Beleuchtung

### LightControllerV2 (26 in Anlage) [SF S.95-99]
- **Zweck:** Lichtsteuerung mit Stimmungen („moods“), Lichtkreisen, Master-Helligkeit/-Farbe, Präsenz, Tageslicht.
- **States:** `activeMoods` (JSON-Array IDs), `moodList` (JSON `[{name, shortName, id, t5, static, used}]`), `favoriteMoods`/`additionalMoods` (ID-Listen),
  `circuitNames` (dynamische Namen der Subcontrols), `daylightConfig`, `presence` (Bitmaske, aktiv wenn Bit0+Bit1), `presenceFrom/To` (Anlage).
- **Details:** `masterValue` (UUID Subcontrol Master-Helligkeit), `masterColor` (UUID Master-RGB), `movementScene`, `hasHistory`, `controlHistory`.
- **Befehle:** `changeTo/<id>` (nur diese Stimmung; 0 = Aus), `addMood/<id>`, `removeMood/<id>`, `plus`, `minus`, `learn/<id>/<name>`, `delete/<id>`, `moveFavoriteMood`,
  `moveAdditionalMood`, `addToFavoriteMood`, `removeFromFavoriteMood`, `setmoodname`, `setcircuitnames`, `setdaylightconfig`, `presence/on|off`.
  Feste IDs: 0 Aus, 98 Wecker, 99 Alles an, -1 benutzerdefiniert, -3 Mehrfachmischung; LoxPanel nutzt 778 als „Aus“ (W:5136).
- **Untersteuerungen:** je Lichtkreis ein Subcontrol vom Typ `Dimmer` (Master-Helligkeit + Dimmkreise), `ColorPickerV2` (Master-Farbe + RGB/Lumitech/TunableWhite-Kreise), `Switch`.
- **App-Darstellung:** Kachel = Name + aktive Stimmung(en); Detail = Stimmungsliste (Favoriten oben, „Weitere“ getrennt), Mischen mehrerer Stimmungen, Lichtkreise mit
  Schalter/Dimmer/Farbwähler, Master-Regler [KB lichtsteuerung-v2: Master skaliert relativ; Kreis-Bezeichnungen aus Config; Verlauf max. 100 Einträge] (Aufbau im Detail: Beobachtung nötig).
- **Fallstricke:** Mehrere aktive Stimmungen möglich (Mischung, pro Ausgang höchste Helligkeit); `moodList`-Reihenfolge = Listenreihenfolge; Subcontrols nur lesbar über `subControls`.
- **LoxPanel: teilweise.** K W:5101-5137 (Glühbirne gelb, Mini-Prev/Next, Doppeltipp = Aus); D W:6612-6651 (Stimmungsliste, Aus-Knopf, heller/dunkler über
  `__dimall` für alle Kreise). **Fehlt:** einzelne Lichtkreise schalten/dimmen, Master-Regler, Farbwähler (ColorPickerV2-Subcontrols), Favoriten-/Zusatz-Trennung,
  Mischen (`addMood/removeMood`), Präsenz-Schalter, Verlauf (`gethistory`).

### LightController (alt), LightsceneRGB [SF S.94-99]
- LightController: States `activeScene`, `sceneList`; Befehle `<n>`, `off`, `on`, `plus`, `minus`, `<n>/learn/<name>`. **LoxPanel voll** (K W:5379, D W:6668).
- LightsceneRGB: States `activeScene`, `color`; Befehle `<n>`, `<n>/learn`. **LoxPanel: fehlt.**

### Dimmer / EIBDimmer [SF S.59-60]
States `position, min, max, step`; Befehle `on`, `off`, `<pos>`. LoxPanel voll (K W:5243, D W:7186). In der Anlage nur als Subcontrol.

### ColorPickerV2 / ColorPicker (nur Subcontrol) [SF S.54-56]
States `color` (Text `hsv(h,s,v)` bzw. `temp(helligkeit,kelvin)`), `sequence`, `sequenceColorIdx`; Details `pickerType (Rgb|Lumitech|TunableWhite)`, `TWMin/TWMax`;
Befehle `hsv(h,s,v)`, `temp(b,k)`, `daylight(b)`, `setFav/<idx>/<farbe>`, `setSequence/...`, `setBrightness`. LoxPanel: nur eigenständig (K W:5284, D W:7296), aus
LightControllerV2 wird nur die Live-Farbe fürs Icon gelesen (W:5107-5116).

## B2. Beschattung / Öffnungen

### Jalousie (16 in Anlage) [SF S.87-90]
- **Zweck:** Jalousie/Rollladen/Vorhang, optional Automatik (`isAutomatic`, Sonnenstand/Beschattung), Dachfenster-Beschattung (type 502), Automatik-Jalousie (348).
- **States:** `position` (0 = oben/offen … 1 = unten/zu), `shadePosition` (Lamelle 0 waagerecht … 1 senkrecht), `up`, `down` (Fahrt), `targetPosition`,
  `targetPositionLamelle`, `autoAllowed`, `autoActive`, `autoState`, `autoInfoText`, `safetyActive`, `locked` (QI, überstimmt Sicherheit), `infoText` (Grund),
  `deviceState` (0 kein Gerät, 1 offline, 2 online), `adjustingEndPos`.
- **Details:** `animation` (0 Jalousie, 1 Rollladen, 2 Vorhang beidseitig, 4/5 links/rechts), `isAutomatic`, `hasHistory`, `type`.
- **Befehle:** `up`, `UpOff`, `down`, `DownOff`, `FullUp`, `FullDown`, `shade`, `auto`, `NoAuto`, `manualPosition/<0-100>`, `manualLamelle/<0-100>`,
  `manualPosBlind/<pos>/<lamelle>`, `stop`, `setAdjustingEndPos` / `endPosAdjustment` (nur Experten, regelmäßig wiederholen).
- **App-Darstellung:** Positionsanzeige (Icon fährt, `animation` bestimmt Piktogramm), Auf/Ab-Tasten, Stellregler Position+Lamellen, Automatik-Umschalter, `infoText`/`autoInfoText`
  als Statuszeile (Beobachtung nötig für Details).
- **Fallstricke:** Position 0..1 vs. Befehl 0..100; „Auf“ = Position 0; bei `locked`/`safetyActive` verweigert der Baustein Fahrten; `Up`/`Down` laufen bis `…Off`
  (LoxPanel nutzt `Up`/`Down`/`Stop`, funktioniert – Stop als Groß-S).
- **LoxPanel: teilweise.** K W:5138-5176 (Fahrtanimation, Auf/Ab, Piktogramm-Position), D W:6722-6751 (Auf/Ab, Ganz auf/Beschatten/Ganz ab, Statuszeile `_jal_status` W:2489).
  **Fehlt:** Position-/Lamellenregler (`manualPosition/manualLamelle` 0 Treffer), Automatik ein/aus (`auto/NoAuto` 0 Treffer), Anzeige `safetyActive/locked/infoText`,
  Lamellenwinkel, `deviceState` offline, Verlauf.

### Gate (1) [SF S.68-69]
States `position` (1 = offen), `active` (-1 schließt, 0, 1 öffnet), `preventOpen`, `preventClose`; Details `animation` (0 Garagentor ... 5), `hasHistory`;
Befehle `open`, `close`, `stop`, `forceOpen`, `forceClose`, `PartiallyOpen` (14.2), `getState`. **LoxPanel voll** (K W:5177, D W:6899); `PartiallyOpen/forceOpen/forceClose`
und `preventOpen/Close`-Anzeige fehlen.

### Window (Dachfenster), WindowMonitor (1) [SF S.141-143]
- Window: `position`, `direction`, `lockedReason`, `targetPosition`, `type`; Befehle `open/on|off`, `close/on|off`, `fullopen`, `fullclose`, `moveToPosition/<0-100>`, `slightlyOpen`, `stop`. LoxPanel K W:5260, D W:7221.
- WindowMonitor: States `windowStates` (CSV je Fenster, Bitmaske 1 zu, 2 gekippt, 4 offen, 8 verriegelt, 16 entriegelt; keine Zahl = offline), `numOpen/numClosed/numTilted/numOffline/numLocked/numUnlocked`;
  Details `windows[{uuid,name,room,installPlace}]`. **LoxPanel voll** (K W:5394, D W:6686). Hinweis: Code testet Bit 32 = offline (W:6694) – laut Doku ist „offline“ *kein Bit*, sondern ein fehlender Wert (Prüfen).

### CentralJalousie / CentralLightController / CentralAlarm / CentralAudioZone / CentralGate / CentralWindow / CentralPresence (je 1 der ersten vier) [SF S.42-43]
Details `controls[{uuid,id}]`; Befehle über `selectedcontrols/...` (siehe A4); `CentralJalousie` hat zusätzlich State `safetyActive`. **LoxPanel voll** (K W:5521-5543, D W:6377-6460), implementiert
eigene Auflösung statt `selectedcontrols`. Nicht umgesetzt: CentralPresence (kein Handler).

## B3. Klima / Heizung / Lüftung

### IRoomControllerV2 (1: „OG Bad“) [SF S.72-79]
- **States:** `tempActual`, `tempTarget`, `activeMode` (0 Eco, 1 Komfort, 2 Gebäudeschutz, 3 Manuell, 4 Aus), `operatingMode` (0 Auto Heizen+Kühlen, 1 Auto nur Heizen, 2 Auto nur Kühlen,
  3-5 manuell analog, -1 Aus), `currentMode`, `prepareState` (-1 kühlt vor, 0, 1 heizt vor), `overrideEntries`/`overrideReason`, `openWindow`, `comfortTemperature(+Cool,+Offset,+Tolerance)`,
  `absentMin/MaxOffset`, `frostProtectTemperature`, `heatProtectTemperature`, `shadingHeat/CoolTemp`, `shadingOut`, `co2`, `humidityActual`, `fan`, `ventMode`, `capabilities`, `actualOutdoorTemp`,
  `averageOutdoorTemp`, `temperatureBoundaryInfo`, `useOutdoor`, `airDeviceState`.
- **Details:** `timerModes[{name,id}]`, `connectedInputs` (Bitmaske gesperrte Einstellungen), `possibleCapabilities`, `SingleComfortTemperature`, `sources[{name,uuid}]`, `linkedAcControls`, `format`, `hasHistory`.
- **Befehle:** `override/<modeId>/[<bis>]/[<temp>]`, `stopOverride`, `setComfortTemperature/<t>`, `setComfortTemperatureCool`, `setManualTemperature/<t>`, `setOperatingMode/<m>`,
  `setComfortModeTemp`, `setAbsentMin/MaxTemperature`, `setComfortTolerance`, `setshadingtemperatureheat/cool`, `setHeatingBoundary/setCoolingBoundary`, `activatePresenceSchedule`,
  `increasetemperature/decreasetemperature/<delta=0.5>`, `setFan`, `setAirDir`.
- **Untersteuerung:** Daytimer (Zeitplan). Einträge codieren Temperatur: `nVal = (uint32)dVal; Modus = nVal & 0xFF; ab Bit 5 benutzerdefinierte Temperatur: Bit6 Heizen, Bit7 Kühlen; Temp×10 = (int16)(nVal >> 8)`.
- **App-Darstellung:** [KB] aktueller Temperaturmodus (Aus/Eco/Komfort/Gebäudeschutz/Manuell/Manuell-Kalender), Heizt/Kühlt-Zustand, „Boost“-Anzeige in der Vorbereitungsphase oder bei
  Abweichung > 1,5 °C, Präsenz-Taste (Komfort bis nächster Zeitplaneintrag, max. 48 h), Timer (Komfort/Eco verlängern), Fenster-offen-Hinweis, Quellen-Dialog, Verlauf; Zeitplan-Anzeige nicht beschrieben.
- **Fallstricke:** Temperaturen kommen in der Miniserver-Einheit (`tempUnit`); -1000 = keine Außentemperatur; „Gebäudeschutz“ existiert separat.
- **LoxPanel: teilweise.** K W:5184-5197 (Ist → Soll, heizt/kühlt, Fenster); D W:6915-6957 (Ist groß, Komfort ± 0,5 K, Zeitleiste `_irc_schedule`, Modi als 1-h-Override + Auto).
  **Fehlt:** Betriebsart wählen (`setOperatingMode`, Heizen/Kühlen/Auto), Präsenz-Taste, manuelle Solltemperatur (`override/3/...` + Temp), Eco-/Schutz-Temperaturen, Kühl-Komfort, Quellen,
  Timer mit frei wählbarer Dauer, Verlauf, Feuchte/CO2.
- IRoomController (v1) [SF S.79-81] voll in LoxPanel (K gemeinsam, D W:6958). ClimateController/ClimateControllerUS [SF S.45-53]: nur US-Variante (K W:5429, D W:7404); ClimateController (nicht US) **fehlt**.

### Ventilation (1: „Raumlüftungssteuerung“) [SF S.136-141]
- **States:** `speed` (%), `mode`, `activeMode`, `ventReason` (0 Grund, 1 erhöht, 4 Stop, 5 Fenster offen, 6 Turbo, 7 Manuell, 8 Abluft, 9 Einschlaf, 10 Frostschutz), `temperatureSupport`, `activeTimerProfile`
  (-1 manuell, -2 keiner, -3 jemand ändert), `overwriteUntil`, `stoppedBy`, `controlInfo` (JSON `{level 0 ok|1 Fehler|2 Warnung|3 Info, title, desc, link, action{name,cmd}}`),
  `presenceMin/Max`, `absenceMin/Max`, `humidityIndoor/Max`, `airQualityIndoor/Max`, `temperatureIndoor/Outdoor/Target`, `frostTemp`, `heatExchanger`.
- **Details:** `modes[{id,name}]`, `timerProfiles[{name,useCase,interval,speed{value,enabled},modes[],defaultMode}]`, `type` (0 generic, 1 Leaf), `has*`-Flags.
- **Befehle:** `setTimer/<interval>/<speed>/<modeId>/<profilIdx>` (-1 = manuell), `setTimer/0` (stoppt), `setAbsenceMin/Max`, `setPresenceMin/Max`, `ackFilterChange`.
- **LoxPanel: nur Anzeige.** K W:5269, D W:7234-7253 (Stufe als read-only-Fläche; Kommentar: Stellbefehle nicht an echter Anlage geprüft). Fehlt: Timer/Modi/Profile, `controlInfo`-Meldungen (Filterwechsel!), Min/Max.

### AcControl [SF S.150-154]
States `status, mode (1-5), fan, ventMode, targetTemperature, temperature, minTemp/maxTemp, pauseUntil/Reason, Override, silentMode`; Befehle `on/off/toggle, setTarget, setMode, setFan, setAirDir, setoverride/..., startpause/<s>`. LoxPanel K W:5422, D W:7331 (nicht in Anlage).

## B4. Schalten, Taster, Eingaben

### Switch (55) [SF S.131]
States `active`, `lockedOn`; Befehle `on`, `off`; Details `type`. **LoxPanel voll:** K W:5206 (Mini-Schieber toggelt, Tap öffnet Detail), D W:6862. `lockedOn` (nicht abschaltbar) nicht ausgewertet.

### Pushbutton (14) [SF S.110]
States `active`; Befehle `pulse` (kurz), `on`/`off` (halten); Details `type` (511 = **Szene**, 71 = virtueller Eingang als Taster, fehlend = Taster-Baustein), `controlReferences`. **LoxPanel voll:** K W:5325, D W:6839
(Auslösen = `pulse`, lokaler Auslöse-Verlauf). Szenen (type 511) werden gleich behandelt.

### TimedSwitch (6) [SF S.133]
States `deactivationDelay` (>0 Rest-Sek., 0 aus, -1 dauerhaft an), `deactivationDelayTotal`; Details `isStairwayLs`; Befehle `on` (dauerhaft), `off`, `pulse` (Treppenhauslicht: startet/restartet; Komfortschalter: schaltet aus).
**LoxPanel voll** (K W:5218, D W:6874). Detail-„Ein“ sendet `pulse` (Zeitlauf), kein dauerhaftes `on`.

### Slider (7), UpDownAnalog, ValueSelector, TextInput [SF S.120, 135-136, 132]
Slider: States `value, error`; Details `min,max,step,format`; Befehl `<zahl>`. LoxPanel Slider voll (K W:5357, D W:7028); ValueSelector/UpDownAnalog/TextInput **teilweise** (`PARTIAL_TYPES`, W:598).

### Radio (2) [SF S.112-113]
States `activeOutput` (0 = aus); Details `outputs{1..16: Name}`, `allOff` (Name für „aus“); Befehle `<id>`, `reset`, `next`, `prev`. **LoxPanel voll** (K W:5370, D W:6652; `next/prev` ungenutzt).

### InfoOnlyAnalog (80), InfoOnlyDigital (18), InfoOnlyText, TextState (20) [SF S.70-72, 132]
- InfoOnlyAnalog: State `value`; Details `format` (C-Format, z. B. `%.1f°C`). InfoOnlyDigital: State `active`; Details `text{on,off}`, `color{on,off}`, `image{on,off}` (+`onColor/offColor`). InfoOnlyText: State `text`. Keine Befehle (rein lesend, ggf. `restrictions` Bit1).
- TextState („Status“-Baustein): `textAndIcon` (Text-Event mit Icon-UUID), `iconAndColor` (JSON `{icon, color}`). Icon per UUID/Pfad holen (SVG, s. A1).
- **LoxPanel voll:** K W:5334-5365, D W:7054-7066; Farben/Icons über `iconAndColor` (W:2867, 2878). `InfoOnlyDigital.details.color/image` nur teilweise ausgewertet. Formate/Einheiten über `_fmt_num` (W:2460, inkl. kW→MW-Skalierung).

### Tracker (7) [SF S.134]
State `entries` (Zeilen durch `|` getrennt, `\x14` = Zeilenumbruch), Details `maxEntries`. **LoxPanel voll:** K W:5444, D W:7009 (Zeitstempel getrennt, `_TS_RE` W:612).

### Sauna, SteakThermo, Remote, UpDownLeftRight, Sequential
Siehe B8. LoxPanel: Sauna (K W:5491, D W:7574), SteakThermo (K W:5509, D W:7644), UpDownDigital (K W:5281, D W:7282); Remote/Sequential **fehlen**.

## B5. Zeit/Automatik

### Daytimer (2) [SF S.57-59]
- States `value`, `mode`, `modeList`, `override` (Rest-Zeit), `entriesAndDefaultValue` (Daytimer-Event), `needsActivation`, `resetActive`; Details `analog`, `text{on,off}`, `format`.
- Befehle `pulse` (Eintrag aktivieren, wenn `needActivate`), `default/<wert>`, `startOverride/<wert>/<sekunden>`, `stopOverride`, `set/<n>/<modus;von;bis;needAct;wert>/...`, `modeslist/<...>`.
- Varianten: IRC-Daytimer v2 (Wert codiert Temperatur, s. B3), IRC-Daytimer (`setc`/`modeslistc`), Pool-Daytimer.
- **LoxPanel: teilweise.** K W:5237, D W:7161 (Wert, Modus, Override-Dauern 15/30/60/90 min, Timer beenden). **Fehlt:** Einträge anzeigen/bearbeiten (`set`), `default`, `pulse` bei `needsActivation`. Kennung-4-Events werden nicht geparst (s. A3).

### PulseAt (3) [SF S.114]
States `isActive`, `startTime` (Sek. seit Mitternacht), `oneTimePulseDate`, `pulseDuration`, `type`; Befehle `setTime/<s>`, `setOneTimePulse/<datum>` (0 = täglich), `setPulseDuration/<s>`, `pulse`, `setType/<id>`.
**LoxPanel: fehlt auf der Kachel (tote Kachel, /api/types.unsupportedControls)** – obwohl ein Detail existiert (W:7091-7098, nur „Nächster Impuls“, keine Befehle). Es fehlt `nav` in `_control_item_build`.

### AlarmClock (7) [SF S.30-33]
States `isEnabled`, `isAlarmActive`, `entryList` (JSON `{id:{name,isActive,alarmTime(Sek. seit 0:00),modes[],nightLight,daily}}`), `currentEntry`, `nextEntry`, `nextEntryTime` (seit 2009), `nextEntryMode`, `ringingTime`,
`ringDuration`, `snoozeTime`, `snoozeDuration`, `prepareDuration`, `confirmationNeeded`, `deviceState`/`deviceSettings` (Touch Nightlight), `wakeAlarmSoundSettings`; Befehle `snooze`, `dismiss`, `entryList/put/<id>/<name>/<zeit>/<aktiv>/<modi|daily>`,
`entryList/delete/<id>`, `setPrepDuration`, `setRingDuration`, `setSnoozeDuration` (≥ 60), `setBeepOn`, `setBrightnessActive/Inactive`, `setWakeAlarmSound/Volume/SlopingOn`.
**LoxPanel: teilweise.** K W:5409, D W:7131 (Weckzeit-Liste, Schlummern/Aus beim Klingeln, Bearbeiten von Einträgen über Alarm-Helfer W:4820-4945). Fehlt: Dauern/Sounds/Nachtlicht-Einstellungen.

### Hourcounter (1) [SF S.69-70]
States `total` (**Sekunden**), `remaining`, `overdue`, `overdueSince`, `maintenanceInterval`, `lastActivation`, `active`, `stateUnit` (0 Sek., 1 Min., 2 Std., 3 Tage = gewünschte Anzeigeeinheit); Befehle `reset`, `resetAll`.
**LoxPanel: voll, aber Verdacht auf Einheitenfehler:** K W:5441 und D W:7426 formatieren `total` mit `"%.0f h"` ohne Umrechnung/`stateUnit`. Per Doku liefert der Baustein Sekunden → mit Live-Wert prüfen. Kein `reset`.

## B6. Sicherheit / Zutritt

### Alarm (3) [SF S.27-29]
States `armed`, `level` (1 still, 2 akustisch, 3 optisch, 4 intern, 5 extern, 6 Fernalarm), `nextLevel`, `nextLevelAt`/`nextLevelDelayTotal`, `armedAt`/`armedDelayTotal`, `disabledMove`, `startTime`, `sensors` (veraltet → Subcontrols), `events`; `armedDelay`/`nextLevelDelay` **deprecated seit 13.0**;
Details `presenceConnected`; Befehle `on`, `on/<0|1>` (ohne/mit Bewegung), `delayedon`, `delayedon/<0|1>`, `off`, `quit`, `dismv/<0|1>`.
**LoxPanel voll (K W:5403, D W:7107):** Scharf/Verzögert/Unscharf/Quittieren. Nutzt noch `armedDelay` (W:7110, veraltet → `armedAt`); kein Bewegungsmelder-Schalter (`dismv`), keine Level-Namen/Countdown (`nextLevelAt`), keine Melderliste, kein Verlauf (`events`).
Vollbild bei Auslösung: `SEC_ALARM_TYPES` (W:189).

### SmokeAlarm (3) [SF S.120-122]
States `level` (1 Voralarm, 2 Hauptalarm), `nextLevel(+Delay)`, `alarmCause` (Bitmaske: 1 Rauch, 2 Wasser, 4 Temperatur, 8 Lichtbogen), `acousticAlarm`, `testAlarm`, `startTime`, `timeServiceMode`, `areAlarmSignalsOff`, `sensors`; Details `availableAlarms`, `hasAcousticAlarm`; Befehle `mute`, `confirm`, `servicemode/<s>`, `startDrill`.
**LoxPanel voll (K W:5366, D W:7068):** Stumm + Quittieren; `alarmCause` als Text ausgegeben (W:7073, ist laut Doku eine Bitmaske!). Fehlt: Wartungs-/Servicemodus, Probealarm.

### AalEmergency (1: „Panikalarm“) [SF S.26]
States `status` (0 normal, 1 Alarm, 2 Reset aktiv, 3 App-deaktiviert), `disableEndTime`, `resetActive`; Befehle `trigger`, `quit`, `disable/<s>`.
**LoxPanel: fehlt auf der Kachel (tote Kachel).** Detail nur Anzeige (W:7080-7083); kein `trigger/quit`.

### NfcCodeTouch (1) [SF S.90-94]
States `lastuser, lasttag, lastcode, codeDate, historyDate, deviceState, nfcLearnResult, keyPadAuthType`; Details `accessOutputs{q1..q6}`, `place`; Befehle `output/<1-6>` (Impuls; 423 = Nutzer nicht berechtigt), `history`, `codes`, `code/create|update|activate|deactivate|delete`, `nfc/startlearn|stoplearn`.
**LoxPanel: fehlt auf der Kachel.** Detail zeigt nur „letzter Zutritt“ (W:7084). Türöffner-Ausgänge (`output/<n>`, nur mit Visu-Passwort/Recht) fehlen.

### Intercom (2) / IntercomV2 [SF S.81-85]
Intercom: States `bell`, `lastBellEvents` (`YYYYMMDDHHMMSS|…`), `lastBellTimestamp`, `version`; Details `deviceType`, `lastBellEventImages`, `showBellImage`, `videoInfo/audioInfo` (leer – Inhalt in **securedDetails**: `streamUrl`, `alertImage`, user, pass, SIP-host);
Befehl `answer`; Subcontrols: 0-3 Ausgänge (Pushbutton, `pulse`). Bilder `camimage/<uuid>/<ts>`. IntercomV2: `answers`, `muted`, `deviceState`, Video-Einstellungen, `playTts/<idx>`, `mute`, `setAnswers`.
**LoxPanel teilweise:** K W:5198 (klingelt-Zustand), D W:6992 (Livebild nur über **manuell konfigurierte URL**, `/mjpeg?id`; Türtaster = Subcontrol-`pulse`). Nicht genutzt: securedDetails-Stream, Klingel-Verlauf/-Bilder, `answer`. IntercomV2 fehlt.

### PresenceDetector (5) [SF S.113-114]
States `active`, `activeSince`, `activeUntil`, `locked`, `lockedUntil`, `infoText`, `time` (Nachlaufzeit), `events`; Befehle `<wert>`, `time/<v>`, `presence/<s>`, `deactivate/<s>`; Subcontrol Tracker.
**LoxPanel: nur Anzeige** (K W:5386, D W:7099 „Anwesend/Abwesend“); keine Befehle (`presence/deactivate/time`).

### MailBox (1: „Briefkasten“) [SF S.101]
States `mailReceived`, `packetReceived`, `notificationsDisabledInput`, `disableEndTime`; Befehle `confirmMail`, `confirmPacket`, `disableNotifications/<s>`; Subcontrol Tracker. **LoxPanel: nur Anzeige** (K W:5486, D W:7569) – Quittieren fehlt (0 Treffer).

## B7. Energie / Zähler

### Meter (21) [SF S.101-103]
States `actual`, `total`, `totalNeg` (nur bidirectional/storage), `storage` (nur storage), `totalDay/Week/Month/Year`, `totalNegDay/…`; Details `actualFormat`, `totalFormat`, `type` (unidirectional | bidirectional | storage | legacy), `totalFormatNeg`,
`storageFormat`, `storageMax` (= 100 %), `displayType` (0 regulär, sonst z. B. Behälter/Batterie), `powerName`; `statistic`/`statisticV2`; Befehl `reset`.
**LoxPanel voll, aber reduziert:** K W:5352, D W:7023 (nur `actual` + `total`; Verlaufsdiagramm über `statistic/statisticV2` generisch W:5630). Nicht ausgewertet: `type`/`displayType` (Speicher mit Füllstand), `totalNeg` (Einspeisung/Entladung), Tages-/Wochen-/Monats-/Jahreswerte. Anlage-Details enthalten `storageFormat`, `storageMax`, `displayType`, `type`.

### EFM (1) / EnergyManager2 (1) / Fronius (1) / PvProductionForecast / LoadManager / PowerUnit / Wallbox2 / WallboxManager / CarCharger
- EFM [SF S.63-66]: States `Ppwr, Gpwr, Spwr, Pre, Pri, CO2, actual0…N`; Details `nodes` (Baum mit `nodeType Grid|Storage|Production|Load|Wallbox|Group`, `actualEfmState`, `ctrlUuid`), `actualFormat`, `totalFormat`, `storageFormat`, `rest`; Befehle `getNodeValue/<viewType>/<uuids;>`, `get/<viewType>` (actual|day|week|month|year|lifetime). StatisticV2. **LoxPanel voll:** K W:5449, D W:7430 (Radialdiagramm `energy_blocks`, Kennzahlen); keine Tages-/Monatsansicht (`get/<viewType>`).
- EnergyManager2 [SF S.61-63]: States `Gpwr, Spwr, Ppwr, Ssoc, MinSoc, MaxSpwr, loads` (JSON je Last: prio, id, name, uuid, icon, pwr, ppwr, hasActual, active, activatedManually, deactivatedManually, minimumActiveUntil, activeDueToDailyRuntime); Befehle `manage`, `setMinSoc/<v>`, `setMaxSpwr/<v>`, `<lastUuid>/activate|deactivate|automatic`, `order/<uuids,>`. **LoxPanel voll (K W:5462, D W:7475) als Anzeige;** Lasten übersteuern (`activate/deactivate/automatic`) und `setMinSoc/setMaxSpwr` fehlen.
- Fronius [SF S.66-68]: `prodCurr, consCurr, gridCurr, batteryCurr, stateOfCharge, earnings*, prod*Day/Month/Year, …`. LoxPanel voll (K W:5256, D W:7260).
- PvProductionForecast, LoadManager, PowerUnit, Wallbox2/WallboxManager/CarCharger, SpotPriceOptimizer: nicht in Anlage. LoxPanel: nur PvProductionForecast (K W:5472, D W:7509). Übrige **fehlen**.

## B8. Medien / sonstige

### AudioZone (1) / AudioZoneV2 (1) [SF S.34-40]
- AudioZone (Music Server Gen 1): States `playState` (0 Stop, 1 Pause, 2 Play), `power`, `volume`, `maxVolume`, `songName/artist/album/station/genre/cover`, `duration`, `progress`, `shuffle`, `repeat`, `sourceList` (Zonenfavoriten-JSON), `source`, `queueIndex`, `serverState`, `clientState`, EQ-/Volume-Sonderlautstärken;
  Befehle `play/pause/next/prev`, `volume/<n>`, `volstep/<n>`, `progress/<s>`, `shuffle`, `repeat/<0|1|3>`, `on/off`, `source/<1-8>`, `…volume/<0-100>`, `equalizersettings/<csv>`, `mastervolume`.
- AudioZoneV2 (Audioserver Gen 2): schlanker – States `playState, power, volume (ab 14.0), maxVolume, serverState, clientState, bluetooth, presence, isLocked`; Befehle `volUp/volDown/volume/<v>`, `play/pause/prev/next`, `playZoneFav/<id>`, `tts/<text>/<vol>`, `bluetooth/<0|1>`, `presence/on|off`. Titel/Cover/Quelle bei V2 liefert nicht der Miniserver, sondern der **Audioserver-Websocket 7091** (`audioserver*.py`).
- **LoxPanel:** AudioZone teilweise (K W:5292, D W:6752), AudioZoneV2 voll (K W:5305, D W:6780: Cover, Titel, Prev/Play/Next, Lautstärke, Quellen/Favoriten über Audioserver bzw. Sonn-API).

### Webpage (1: Kamera) [SF S.141]
Details `url`, `urlHd`, `image`, `iconColor`. **LoxPanel voll** (K W:5273, D W:7275, iframe `k:"web"`).

### Irrigation (2) [SF S.85-87]
States `currentZone` (-1 aus, 0.. Zone, 8 alle), `zones` (JSON `[{id,name,duration,setByLogic}]`), `rainActive`, `rainTime`, `expectedPrecipitation`, `maxExpectedPrecipitation`; Befehle `start` (nur wenn zu trocken), `startForce`, `stop`, `setDuration/<zone>=<s>`, `setDurations/...`, `select/<zone>` (0 = aus, 9 = alle).
**LoxPanel teilweise** (K W:5478, D W:7529): Start/Erzwingen/Stopp; Zonen reine Anzeige. Fehlt: Zone manuell starten (`select`), Dauer ändern (`setDuration`).

### Weitere Typen der Doku, die in der Anlage nicht vorkommen
| Typ | Kern | LoxPanel |
|---|---|---|
| AalSmartAlarm [S.26] | `alarmLevel, isLocked, isLeaveActive`; `confirm/disable/startDrill` | fehlt |
| AlarmChain [S.29] | `activeAlarmType` (Bitmaske), `nextAlarmLevelAt`, `activeAlarmText`; `quit` | fehlt |
| Application [S.33] | `url`, `image`, `iconColor` | Link-Handling grob (W:10873 betrifft Admin, nicht dieser Typ) – fehlt als Typ |
| CarCharger [S.41] | `charging, connected, power, limitMode`; `charge/on|off`, `limit/<kW>` | fehlt |
| Heatmixer [S.69] | `tempTarget, tempActual` | fehlt |
| LoadManager [S.99] | `currentPower, maxPower, availablePower, lockedLoads` | fehlt |
| MsShortcut [S.103] | `localUrl, remoteUrl, serialNr` | fehlt |
| PoolController [S.104-110] | viele (Zyklen, Ventil, Temperatur) | fehlt |
| Remote [S.114-117] | Medien-Fernbedienung: `mode/<id>`, Tasten | fehlt |
| Sauna [S.117-119] | `temp/humidity/mode/on/off/…` | voll (K W:5491, D W:7574) |
| Sequential [S.119] | `triggerSequence/<id>` | fehlt |
| SolarPumpController [S.122] | `bufferTemp<n>, collectorTemp` | fehlt |
| SpotPriceOptimizer [S.123] | `current, active, getForecasts` | fehlt |
| StatusMonitor [S.125] | `numState0-9`, `inputStates`, `details.inputs/status` | fehlt |
| SteakThermo [S.126] | Fühlertemperaturen, Timer, Alarme | voll (K W:5509, D W:7644) |
| SystemScheme [S.131] | Bild + Controls an Positionen | voll (K W:5435, D W:6610) |
| UpDownLeftRight digital/analog [S.134-135] | `UpOn/UpOff/PulseUp/…`, bzw. `value`+min/max | digital voll (W:5281, 7282), analog teilweise |
| IntercomV2 [S.83] | siehe B6 | fehlt |
| ClimateController (nicht US) [S.45] | `currentMode, autoMode, controls[]` | fehlt |

---

# C) Lücken & Chancen für LoxPanel (priorisiert, max. 15)

Priorität = Nutzen für die vorhandene Anlage × Aufwand-Nutzen-Verhältnis. Belege: Code-Grep (0 Treffer) und `/api/types`.

1. **Tote Kacheln für PulseAt (3), AalEmergency (1), NfcCodeTouch (1).** `/api/types` listet sie unter „Nicht unterstützte Controls“; `_control_item_build` hat keinen Zweig (W:5101-5566), das Detail existiert aber (W:7080-7098) und ist nur lesend. → Kacheln mit `nav` anbinden;
   Panikalarm braucht `trigger`/`quit`, PulseAt `pulse`/`setTime`, NFC `output/<n>` (Visu-Passwort).
2. **Jalousie (16 Stück): keine Position-/Lamellensteuerung, keine Automatik.** `manualPosition`, `manualLamelle`, `manualPosBlind`, `auto`, `NoAuto` kommen im Code 0× vor; Detail nur Auf/Ab/Ganz/Beschatten (W:6722-6751). Die App bietet Regler und Automatik-Schalter [SF S.88-89]. `isAutomatic`/`autoActive` stehen in der Anlage zur Verfügung.
3. **Sperrstatus `jLocked` und `restrictions` werden ignoriert** (0 Treffer in W). Alle Anlagen-Typen haben `jLockable`. Gesperrte Bausteine nehmen Befehle ohne Meldung nicht an; Jalousie hat zusätzlich `locked`/`safetyActive`/`infoText` (nur `autoInfoText` wird genutzt, W:2489). → Schloss-/Sperr-Hinweis auf Kachel und Detail, Befehle sperren.
4. **LightControllerV2 (26): keine Lichtkreise, kein Master, keine Farbe, kein Mischen.** Detail kennt nur Stimmungen + „heller/dunkler“ (W:6612-6651); Subcontrols (Dimmer/Switch/ColorPickerV2) und `masterValue/masterColor` bleiben ungenutzt. Die App zeigt diese Ebene [KB lichtsteuerung-v2]. Außerdem keine Trennung Favoriten-/Zusatzstimmungen (`favoriteMoods/additionalMoods`) und kein `addMood/removeMood`.
5. **IRoomControllerV2: Betriebsart, Präsenz, manuelle Temperatur und Eco-/Schutz-Werte fehlen** (W:6915-6957). `setOperatingMode` (Heizen/Kühlen/Auto), `activatePresenceSchedule`/Präsenz-Taste [KB: Komfort bis nächster Eintrag, max. 48 h], `override/3/<bis>/<temp>` und `setAbsentMin/Max` sind in [SF S.77-78] beschrieben. Nur 1 Regler in der Anlage, aber zentrales Bedienelement.
6. **Ventilation nur Anzeige** (`PARTIAL_TYPES`, W:7234-7253): `setTimer`, Modi, Timerprofile, `controlInfo` (Fehler/Filterwechsel mit Quittierung `ackFilterChange`) fehlen – Meldungen wie „Filter wechseln“ sieht man im Panel nie. In der Anlage vorhanden: `modes`, `timerProfiles`, `controlInfo`, `stoppedBy`.
7. **Meter (21): nur `actual` und `total`.** `type` bidirectional/storage, `totalNeg`, `storage`/`storageMax`/`displayType` (Anlage-Details vorhanden) sowie Tag/Woche/Monat/Jahr (`totalDay`…) werden nicht angezeigt (W:7023-7027). Wirkt sich auf Speicher-/Einspeise-Zähler aus.
8. **MailBox, Irrigation, PresenceDetector, Alarm sind lesend/unvollständig, obwohl Befehle existieren:** MailBox `confirmMail/confirmPacket` (0 Treffer), Irrigation `select/<zone>` und `setDuration` (0 Treffer, Zonen „reine Anzeige“ W:7552), Präsenzmelder `presence/deactivate/time` (nicht verwendet, W:7099), Alarm `on/<0|1>`, `dismv` (Bewegungsmelder an/aus, 0 Treffer).
9. **Alarm nutzt veraltete States:** `armedDelay` (W:7110) ist seit 13.0 deprecated → `armedAt`/`armedDelayTotal` [SF S.28]; Level-Texte (1 still … 6 Fernalarm), `nextLevelAt`-Countdown und die Melderliste (`sensors` → Subcontrols) fehlen. SmokeAlarm: `alarmCause` ist Bitmaske (Rauch/Wasser/Temperatur/Lichtbogen), wird aber als Text ausgegeben (W:7073).
10. **Hourcounter-Einheit verdächtig:** `total` wird als „h“ formatiert (W:5442, 7428), Doku: Sekunden, Anzeigeeinheit steuert `stateUnit` [SF S.70]. Mit Live-Wert prüfen; evtl. falsche Betriebsstundenanzeige (1 Baustein: Heizstab).
11. **Benachrichtigungen und Systemstatus fehlen.** `globalStates.notifications` (`lvl` Info/Fehler/Systemfehler) und `messageCenter` (Herz/Balken in der App, „Warnung/Kritisch“, Lösungshinweise) kommen im Code 0× vor; die Anlage liefert `notifications`, `pastTasks`, `plannedTasks`. → Meldungsleiste/-liste (Panel hat nur eigene `lpnotify`-Toasts, P:664). Größte Funktionslücke gegenüber der App bei Alarm/Störungen.
12. **Daytimer-Events (Kennung 4) werden nicht geparst** (WS:249-263, nur Log „unbekannte Kennung“). Daytimer (2) zeigen daher Wert/Override, aber keine Einträge; Bearbeiten (`set`, `default`, `pulse`) fehlt ganz. Zu prüfen: wird `entriesAndDefaultValue` der Anlage überhaupt befüllt (der Code liest es als Text, W:2253-2264)?
13. **Verlauf („Control History“) fehlt.** `hasHistory` kommt bei Jalousie, LightControllerV2, IRoomControllerV2, Gate vor; `gethistory` wird nie aufgerufen (0 Treffer). Die App zeigt damit „Warum fährt die Jalousie/geht das Licht an?“.
14. **Intercom: Video nur per manueller URL.** W:6992-7006 holt Stream/Zugangsdaten nicht aus `securedDetails`; kein Klingelverlauf (`lastBellEvents`, `camimage/…`), kein `answer`. In der Anlage 2 Intercoms (Doorbird, Coodeknacker). Aufwand hoch (verschlüsselte Abfrage, [SF S.24]).
15. **Strukturmetadaten ungenutzt:** `defaultRating`/`sortByRating` (App-Sortierung nach Sternen), `cats.type`/`colorShade`, `msInfo.tempUnit` (°F), `msInfo.currency`, `hasControlNotes`, `links`, `preset`, `currentUser.userRights` (Bedien- vs. Leserechte; `restrictions` Bit1 = read-only) – 0 Treffer in W. Relevant für „sieht aus wie die App“ (Sortierung) und Rechtetreue.

**Kleinere Funde:** Gate `PartiallyOpen/forceOpen` und `preventOpen/Close` fehlen; Radio `next/prev` ungenutzt; WindowMonitor testet Offline als Bit 32 (W:6694), Doku kennt kein Bit (kein Wert = offline); AlarmClock: Dauern/Sounds/Nachtlicht nicht einstellbar; Switch `lockedOn` nicht beachtet; Zentralbausteine ohne `selectedcontrols` (nutzt Einzelbefehle – funktioniert, ist aber nicht atomar und umgeht die Berechtigungsprüfung des Miniservers pro Control); `CentralPresence`/`CentralGate/Window` ohne Detailansicht.

**Chancen (kein Muss):** `loxone://`-Deep-Links für Support; Tageslicht-/Wecker-Stimmungen (IDs 98/99) als Sonderfälle der Stimmungsliste kennzeichnen; `statisticV2`-Verlauf für Meter/EFM bereits vorhanden – Tages-/Monatsbalken (`getStatistic/.../diff/...`) ergänzen; `links[]` für „Verknüpfte Bausteine“ (W:7685 deckt das teilweise ab).
