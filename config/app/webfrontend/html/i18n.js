/* LoxPanel Admin-UI Uebersetzung (i18n) fuer /settings und /config.
 *
 * Ansatz: Schluessel = deutscher Quelltext (de ist die Referenz, kein Eintrag
 * noetig). Zusatzsprachen liefern eine Map deutsch->uebersetzt; fehlt ein
 * Eintrag, bleibt der deutsche Text stehen (sichtbarer, aber unschaedlicher
 * Fallback). Gebaeude-/Geraete-/Raum-/Kategorienamen kommen aus dem Miniserver
 * und werden NICHT uebersetzt -> nur explizit markierte Elemente
 * ([data-i18n]) bzw. per T() erzeugte Texte werden angefasst.
 */
(function () {
  var LANGS = [['de', 'Deutsch'], ['en', 'English']];

  var CAT = {
    en: {
      // Statusleiste: Anzeige je Baustein
      'Statusleiste – Anzeige je Baustein': 'Status bar – display per block',
      'Symbol + Text': 'Icon + text',
      'Loxone-Statussymbol statt festem Symbol': 'Loxone status icon instead of fixed icon',
      'Status-Baustein · jetzt: ': 'Status block · now: ',
      'kein Status-Baustein': 'not a status block',
      'Beides': 'Both',
      'Loxone-Symbol': 'Loxone icon',
      // Rahmen / Navigation
      'Einstellungen': 'Settings',
      'Hier legst du fest, WANN Nacht ist – für alle Panels gleich. Nacht ist aktiv, solange der gewählte Betriebsmodus läuft oder der gewählte Baustein eingeschaltet ist. Ohne Auswahl: Sonnenuntergang bis Sonnenaufgang.':
        'Here you define WHEN it is night – the same for all panels. Night is active while the selected operating mode is running or the selected block is switched on. With no selection: sunset to sunrise.',
      'Auslöser – Betriebsmodus oder Baustein': 'Trigger – operating mode or block',
      'Kein Auslöser (nach Sonnenstand)': 'No trigger (by sun position)',
      'Betriebsmodus': 'Operating mode',
      'Konfiguration': 'Configuration',
      'Intercom / Kameras': 'Intercom / cameras',
      'bald': 'soon',
      'Neues Panel': 'New panel',
      '＋ Neues Panel': '＋ New panel',
      'Panels & Kacheln': 'Panels & tiles',
      'Ansichten gestalten': 'Design views',
      'Panels · Miniserver · Intercom': 'Panels · Miniserver · Intercom',
      'Visu öffnen': 'Open visu',
      'Panel-Ansicht anzeigen': 'Show panel view',
      // Miniserver
      'Zugang zum Loxone Miniserver. Nach dem Speichern verbindet der Server sofort neu.':
        'Access to the Loxone Miniserver. Reconnects immediately after saving.',
      'Host / IP': 'Host / IP',
      'Benutzer': 'User',
      'Passwort': 'Password',
      'unverändert lassen': 'leave unchanged',
      'Auslöser – Loxone-Betriebsmodus': 'Trigger – Loxone operating mode',
      '<b>Hier legst du fest, WANN Nacht ist – für alle Panels gleich.</b> Wähle einen Loxone-Betriebsmodus (z. B. „Nacht“): Nacht ist aktiv, solange dieser Modus läuft. Die Betriebsmodi legst du in Loxone Config an. Ohne Auswahl gilt Sonnenuntergang bis Sonnenaufgang (Zeiten vom Miniserver).': '<b>This sets WHEN it is night – the same for all panels.</b> Pick a Loxone operating mode (e.g. “Night”): night is active while this mode is running. Operating modes are created in Loxone Config. Without a choice, sunset to sunrise applies (times from the Miniserver).',
      'Display-Kennwort nicht übernommen, weil Host oder Treiber geändert:': 'Display password not kept because host or driver changed:',
      'Zertifikat prüfen (Gen2 mit selbstsigniertem Zertifikat: aus)':
        'Verify certificate (Gen2 with self-signed cert: off)',
      'Verbinden & Speichern': 'Connect & save',
      // Kamera / Tuerstation
      'Video-URL (MJPEG) und Login der Türstation(en). Wird für das Kamerabild im Intercom-Popup gebraucht. Die Liste kommt aus dem Miniserver.':
        'Video URL (MJPEG) and login of the door station(s). Needed for the camera image in the intercom popup. The list comes from the Miniserver.',
      'Speichern': 'Save',
      // SIP
      'Gegensprechen über die Türstation direkt am Panel (SIP-Audio/-Video statt nur Kamerabild).':
        'Two-way audio via the door station directly on the panel (SIP audio/video instead of just the camera image).',
      'SIP-Anbindung ist in Arbeit.': 'SIP integration is in progress.',
      'Coming soon': 'Coming soon',
      // Panels
      'Panels mit installiertem Agent melden sich automatisch. Ansicht wählen und den Kiosk starten / aktualisieren.':
        'Panels with the agent installed register automatically. Pick a view and start / refresh the kiosk.',
      'Suche Panels…': 'Searching for panels…',
      'Noch kein Panel gefunden. Agent auf dem Panel starten (agent/loxpanel-agent.py).':
        'No panel found yet. Start the agent on the panel (agent/loxpanel-agent.py).',
      '(Standard)': '(Default)',
      'Start': 'Start',
      'Reload': 'Reload',
      'Stop': 'Stop',
      'Kiosk läuft': 'Kiosk running',
      'Status:': 'Status:',
      'Video-URL (MJPEG)': 'Video URL (MJPEG)',
      // Audio
      'Der Weckton (Loxone-Wecker) wird direkt im Kiosk-Browser des Panels erzeugt. Mit dem Test-Ton prüfst du, ob am Panel wirklich etwas zu hören ist — falls nicht, liegt es meist an der Lautstärke/Ausgabe am Gerät (ALSA/PulseAudio), nicht am Browser.':
        'The alarm tone (Loxone alarm clock) is generated directly in the panel’s kiosk browser. Use the test tone to check whether the panel actually plays sound — if not, it is usually the volume/output on the device (ALSA/PulseAudio), not the browser.',
      'Test-Ton': 'Test tone',
      'Sendet 3 kurze Pieptöne an das/die gewählte(n) Panel(s). Es müssen dafür geöffnet sein (Kiosk läuft und zeigt die Visu).':
        'Sends 3 short beeps to the selected panel(s). They must be open (kiosk running and showing the visu).',
      'Ziel-Panel': 'Target panel',
      'Test-Ton senden': 'Send test tone',
      'Alle Panels': 'All panels',
      // Kalender & Wetter (Front / Screensaver)
      'Kalender & Wetter': 'Calendar & weather',
      'Zeigt Termine aus deinen iCal-Abos und das Wetter auf der Uhr-Startseite (Screensaver) aller Panels. Serverweit — der Server holt die Daten und schickt sie an die Panels.':
        'Shows events from your iCal subscriptions and the weather on the clock start page (screensaver) of all panels. Server-wide — the server fetches the data and pushes it to the panels.',
      'iCal-Kalender': 'iCal calendars',
      'Abo-Link aus Apple/iCloud (Kalender → Teilen → Öffentlicher Kalender), Google oder anderen Diensten. webcal:// oder https://. Nur Lesen, kein Login. Mehrere Kalender möglich — Geburtstage, Müllabfuhr, Ferien und die Familientermine landen gemeinsam auf einer Liste.':
        'Subscription link from Apple/iCloud (Calendar → Share → Public calendar), Google or other services. webcal:// or https://. Read-only, no login. Several calendars are possible — birthdays, waste collection, school holidays and family appointments all end up in one list.',
      'Überschrift am Panel': 'Heading on the panel',
      '＋ Kalender hinzufügen': '＋ Add calendar',
      'Feiertags-iCal (optional)': 'Holiday iCal (optional)',
      'z.B. österr. Feiertage aus Google Kalender (basic.ics)':
        'e.g. Austrian public holidays from Google Calendar (basic.ics)',
      'Optionaler zweiter iCal nur für Feiertage — deren Tage werden im Monatsraster rot markiert (wie Sonntage). Z.B. der Feiertagskalender deines Landes aus Google.':
        'An optional second iCal for public holidays only — those days are marked red in the month grid (like Sundays). For example your country’s holiday calendar from Google.',
      // Kalenderzeile
      'Kalender': 'Calendar',
      'Name': 'Name',
      'Farbe': 'Color',
      'Entfernen': 'Remove',
      'iCal-Abo-URL': 'iCal subscription URL',
      'z.B. Müllabfuhr': 'e.g. waste collection',
      'Noch kein Kalender. Mit „＋ Kalender hinzufügen" den ersten Abo-Link eintragen.':
        'No calendar yet. Use “＋ Add calendar” to enter the first subscription link.',
      'Mehr als {max} Kalender gehen nicht.': 'More than {max} calendars are not possible.',
      // Status der Kalender
      'noch nicht geladen': 'not loaded yet',
      'geladen': 'loaded',
      'Termine': 'events',
      'Fehler:': 'Error:',
      'Kalender geladen': 'Calendar loaded',
      'Kein Kalender konfiguriert.': 'No calendar configured.',
      'aus {n} Kalendern': 'from {n} calendars',
      '{n} von {gesamt} Kalendern nicht geladen': '{n} of {gesamt} calendars not loaded',
      'Grund steht oben beim jeweiligen Kalender.':
        'The reason is shown above, at the calendar concerned.',
      'Das Panel zeigt weiter den Stand von {zeit} Uhr.':
        'The panel still shows the data from {zeit}.',
      'Panel zeigt den Stand von {zeit} Uhr.': 'Panel is showing the data from {zeit}.',
      // Wetter
      'Wetter': 'Weather',
      'Hat die Anlage den Loxone-Wetterdienst, kommt das Wetter von dort — die Koordinaten bleiben dann unbenutzt. Sonst von Open-Meteo: kostenlos, ohne API-Schlüssel und ohne Konto, nur die Koordinaten deines Standorts eintragen (Dezimalgrad, z.B. 47.071 / 15.439). Leer lassen schaltet das Wetter aus, solange kein Wetterserver liefert.':
        'If the installation has the Loxone weather service, the weather comes from there — the coordinates then stay unused. Otherwise from Open-Meteo: free, no API key and no account, just enter the coordinates of your location (decimal degrees, e.g. 47.071 / 15.439). Leaving them empty switches the weather off, as long as no weather server delivers.',
      'Breitengrad': 'Latitude',
      'Längengrad': 'Longitude',
      'Wetter vom Loxone-Wetterserver': 'Weather from the Loxone weather server',
      'Open-Meteo wird nicht abgefragt.': 'Open-Meteo is not queried.',
      'Wetter geladen': 'Weather loaded',
      'Standort vom Miniserver wird verwendet.': 'The location from the Miniserver is used.',
      'Kein Standort konfiguriert.': 'No location configured.',
      'Automatisch vom Miniserver:': 'Automatically from the Miniserver:',
      // Anzeige am Panel
      'Anzeige': 'Display',
      'Termine der nächsten … Tage': 'Events for the next … days',
      'Wetter-Vorschau (Tage)': 'Weather forecast (days)',
      'Termine auf der Uhr-Seite (max.)': 'Events on the clock page (max.)',
      'Kalenderfarben am Panel zeigen': 'Show calendar colors on the panel',
      'Aus = schlicht: alle Termine einfarbig, nur der Kalendername steht daneben. An = jeder Kalender bekommt seinen Farbpunkt, auch im Monatsraster.':
        'Off = plain: all events in a single color, only the calendar name beside them. On = every calendar gets its color dot, in the month grid too.',
      '„Termine auf der Uhr-Seite" ist eine Obergrenze — was neben Wetter und Uhr nicht mehr auf den Schirm passt, bleibt weg (auf einem 480×480-Panel sind das etwa drei). Die vollständige Liste steht im Kalender-Pane.':
        '“Events on the clock page” is an upper limit — whatever no longer fits on the screen next to the weather and the clock is left out (on a 480×480 panel that is about three). The full list is in the calendar pane.',
      // Verlaufs-Diagramme (Detailseite, Split-Haelfte, Kachel)
      'Verlauf': 'History',
      'Zeitraum': 'Period',
      'Trend': 'Trend',
      'Tagesmuster': 'Daily pattern',
      'Tagesspanne': 'Daily range',
      'Kurve mit Tief, Hoch und Änderung': 'Curve with low, high and change',
      'Verbrauch als Balken, dazu die Summe': 'Consumption as bars, plus the total',
      'Ein/Aus als Stufen, dazu die Einschaltdauer': 'On/off as steps, plus the time switched on',
      '7 Tage × 24 Stunden als Farbraster': '7 days × 24 hours as a color grid',
      'Tief bis Hoch je Tag, 7 Tage': 'Low to high per day, 7 days',
      '7 Tage': '7 days',
      '30 Tage': '30 days',
      // Neues Panel
      'Neues Panel einrichten': 'Set up a new panel',
      'Erzeugt den Befehl, der Agent + Config aufs Panel überträgt, den Autostart einrichtet und Chromium still stellt (keine Übersetzen-Leiste / Anmeldung). Einmal im Terminal ausführen — fragt nach dem SSH-/sudo-Passwort des Panels.':
        'Generates the command that copies agent + config to the panel, sets up autostart and quiets Chromium (no translate bar / sign-in). Run once in a terminal — it asks for the panel’s SSH/sudo password.',
      'Panel-IP': 'Panel IP',
      'SSH-Benutzer': 'SSH user',
      'Anzeigename': 'Display name',
      'Startansicht (Profil)': 'Start view (profile)',
      'Server-Adresse (dieser Server)': 'Server address (this server)',
      'Befehl erzeugen': 'Generate command',
      'In Zwischenablage kopieren': 'Copy to clipboard',
      'Panel-IP und Server-Adresse nötig': 'Panel IP and server address required',
      '✓ kopiert': '✓ copied',
      'Kopieren nicht möglich – bitte manuell markieren': 'Copy failed – please select manually',
      'Fehler': 'Error',
      'Keine Intercom-Bausteine gefunden (Miniserver verbunden?).':
        'No intercom blocks found (Miniserver connected?).',
      '✓ Gespeichert': '✓ Saved',
      'Nicht übernommen:': 'Not kept by the server:',
      'verbunden': 'connected',
      'nicht verbunden': 'not connected',

      // ---- Betriebsmodus-Automatik (/settings) ----
      'Betriebsmodus-Automatik': 'Operating-mode automation',
      'Loxone schaltet die Ansicht automatisch um: in Loxone Config einen virtuellen HTTP-Ausgang anlegen, der pro Betriebsart einen Modusnamen an diesen Server schickt. Hier legst du je Panel fest, welche Ansicht bei welchem Modus erscheint. Panel ohne Eintrag für einen Modus bleibt unverändert.':
        'Loxone switches the view automatically: in Loxone Config create a virtual HTTP output that sends a mode name to this server per operating mode. Here you define, per panel, which view appears for which mode. A panel without an entry for a mode stays unchanged.',
      'Panels mit Agent (Linux) erscheinen automatisch. Ein Panel ohne Agent (z.B. NSPanel Pro, Tablet) muss nur die Visu mit einer Geräte-Kennung öffnen: ?panel=<start>&device=<name> — dann wird es hier gelistet und live umgeschaltet (Browser lädt sich mit neuem Profil neu, kein Agent nötig).':
        'Panels with an agent (Linux) appear automatically. A panel without an agent (e.g. NSPanel Pro, tablet) just opens the visu with a device id: ?panel=<start>&device=<name> — then it is listed here and switched live (the browser reloads with the new profile, no agent needed).',
      'Noch kein Panel bekannt. Ein Panel muss sich einmal gemeldet haben (Agent läuft), dann erscheint es hier.':
        'No panel known yet. A panel must have reported in once (agent running), then it appears here.',
      'Automatik speichern': 'Save automation',
      '— Ansicht wählen —': '— choose view —',
      'Modus (z.B. gaeste)': 'Mode (e.g. guests)',
      'Automatik aktiv': 'Automation active',
      '+ Modus': '+ Mode',
      'Zeile entfernen': 'Remove row',

      // ---- /config (Panel-Editor) ----
      'Titel': 'Title',
      'Fenstertitel des Panels.': 'Window title of the panel.',
      'Kiosk-URL:': 'Kiosk URL:',
      'Standard-Aussehen für <b>alle</b> Panels. Einzelne Panels können es unter „Darstellung" überschreiben (leer = erbt global).':
        'Default look for <b>all</b> panels. Individual panels can override it under "Appearance" (empty = inherits global).',
      'Untere Leiste (Tabs)': 'Bottom bar (tabs)',
      'Bis zu <b>4 Buttons</b> — die 4 Standard-Tabs und/oder einzelne Kategorien als Abkürzung. Der <b>erste aktive</b> ist die Startseite (★). ':
        'Up to <b>4 buttons</b> — the 4 standard tabs and/or individual categories as shortcuts. The <b>first active</b> one is the start page (★). ',
      'Räume': 'Rooms',
      'Welche Räume dieses Panel zeigt. <b>Nichts angehakt = alle Räume.</b>':
        'Which rooms this panel shows. <b>Nothing checked = all rooms.</b>',
      'Alle abwählen': 'Deselect all',
      'Kategorien': 'Categories',
      'Welche Kategorien im Tab „Kategorien" erscheinen. <b>Nichts angehakt = alle.</b> Bei gesetzter Raum-Auswahl werden Kategorien zusätzlich auf diese Räume gefiltert.':
        'Which categories appear in the "Categories" tab. <b>Nothing checked = all.</b> If a room selection is set, categories are additionally filtered to those rooms.',
      'Kacheln gestalten': 'Style tiles',
      'Klicke eine Kachel an und ändere <b>Farben, Schrift und Icon nur für diese Kachel</b> (auf diesem Panel). Farbiger Punkt = schon angepasst. Mit dem <b>Auge</b> rechts blendest du eine Kachel auf diesem Panel ganz aus. ':
        'Click a tile and change <b>colors, font and icon for this tile only</b> (on this panel). Colored dot = already customized. Use the <b>eye</b> on the right to hide a tile entirely on this panel. ',
      'Kachel suchen…': 'Search tile…',
      'Darstellung (optional)': 'Appearance (optional)',
      'Überschreibt das globale Theme nur für dieses Panel. Leer = global.':
        'Overrides the global theme for this panel only. Empty = global.',
      'Aktiv-Overlay': 'Active overlay',
      'Wie eine Kachel im <b>aktiven Zustand</b> hervorgehoben wird (an = Akzent, ok = grün, kritisch = rot): Rahmen, Füllung und Deckkraft. Die <b>Farbe</b> kommt je Zustand aus dem Theme, hier stellst du das <b>Aussehen</b> ein. Gilt für dieses Panel — einzelne Kacheln können unten abweichen.':
        'How a tile is highlighted in its <b>active state</b> (on = accent, ok = green, critical = red): border, fill and opacity. The <b>color</b> per state comes from the theme; here you set the <b>look</b>. Applies to this panel — individual tiles can differ below.',
      'Panel löschen': 'Delete panel',
      'Kein Panel gewählt.': 'No panel selected.',
      'keine Kacheln im gewählten Raum-/Kategorie-Filter': 'no tiles in the selected room/category filter',
      'nichts gefunden': 'nothing found',
      // Labels
      'Icon-Größe': 'Icon size',
      'Name-Größe': 'Name size',
      'Sub-Größe': 'Sub size',
      'Schriftart': 'Font',
      'Schriftfarbe (Name)': 'Text color (name)',
      'Sprache': 'Language',
      'Steuert vorerst Datum & Uhr am Panel. Gerätenamen kommen aus dem Miniserver.':
        'For now controls date & clock on the panel. Device names come from the Miniserver.',
      'Horiz. Versatz (px)': 'Horiz. offset (px)',
      'Display aus nach (Sek.)': 'Display off after (sec.)',
      'Auto-Neustart alle (Std.)': 'Auto-restart every (hrs.)',
      'Kacheln pro Zeile': 'Tiles per row',
      'Füllung': 'Fill',
      'Rahmen': 'Border',
      'Rahmenbreite': 'Border width',
      'Darstellung': 'Appearance',
      'Hintergrund': 'Background',
      'Icon-Farbe': 'Icon color',
      'Textfarbe': 'Text color',
      'Schrift': 'Font',
      // Optionen
      'Standard (global)': 'Default (global)',
      'System (Sans)': 'System (Sans)',
      'Eigene…': 'Custom…',
      'Rahmen + Füllung': 'Border + fill',
      'Nur Rahmen': 'Border only',
      'Nur Füllung': 'Fill only',
      '2 × 2 (4″-Panel)': '2 × 2 (4″ panel)',
      '3 × 2 (Tablet)': '3 × 2 (tablet)',
      'Standard (Deutsch)': 'Default (German)',
      // Icon-Reiter / Kachel-Editor
      'Eingebaut': 'Built-in',
      'Google · Upload': 'Google · Upload',
      'Kachel zurücksetzen': 'Reset tile',
      'Standard': 'Default',
      'Alle einblenden': 'Show all',
      'Auf Standard zurücksetzen': 'Reset to default',
      'neutral': 'neutral',
      'Aktiv': 'Active',
      // Global-Editor
      '🌐 Globale Darstellung': '🌐 Global appearance',
      'Schrift, Größe, Farbe und Stärke der Kachel-Beschriftung — gilt global für alle Panels.':
        'Font, size, color and weight of the tile labels — applies globally to all panels.',
      'Kategorie-Farben (Ampel)': 'Category colors (traffic light)',
      'Pro Kategorie eine <b>Aktiv-</b> und <b>OK-Farbe</b> für Kachel-Hintergrund und Rahmen — gilt systemweit auf allen Panels (Wiedererkennung). ◐ einschalten = Zustands-Ampel (z. B. Alarm rot/grün, Tor gelb/grün). Aus = neutral. Analoge Messwerte bleiben immer neutral.':
        'Per category an <b>active</b> and an <b>OK</b> color for tile background and border — applies system-wide on all panels (recognizability). Turn on ◐ = state traffic light (e.g. alarm red/green, gate yellow/green). Off = neutral. Analog readings always stay neutral.',
      // Dialoge
      'ID des neuen Panels (klein, ohne Leerzeichen), z. B. wohnzimmer:':
        'ID of the new panel (lowercase, no spaces), e.g. livingroom:',
      'Ungültige ID.': 'Invalid ID.',
      // Gerät hinzufügen / Meine Geräte (Vereinheitlichung)
      'Welches Gerät?': 'Which device?',
      'Erst das Gerät wählen – danach siehst du nur die passenden Schritte.': 'Pick the device first – then you only see the matching steps.',
      'Android-Geräte (Shelly, Sonoff, Tablet) richtet LoxPanel auf Wunsch automatisch ein: per ADB über WLAN, ohne Kabel und ohne Eingaben am Gerät außer einer Bestätigung. Linux-Panels bekommen den Agenten per SSH. iPad, iPhone und Browser brauchen nur die Adresse.': 'LoxPanel can set up Android devices (Shelly, Sonoff, tablet) automatically: via ADB over Wi-Fi, no cable and nothing to enter on the device except one confirmation. Linux panels get the agent via SSH. iPad, iPhone and browsers only need the address.',
      'Shelly Wall Display': 'Shelly Wall Display',
      'Sonoff NSPanel Pro': 'Sonoff NSPanel Pro',
      'Wandpanel (Android)': 'Wall panel (Android)',
      'Android-Tablet oder Handy': 'Android tablet or phone',
      'mit Fully Kiosk': 'with Fully Kiosk',
      'Linux-Panel': 'Linux panel',
      'Agent per SSH': 'Agent via SSH',
      'iPad, iPhone oder Browser': 'iPad, iPhone or browser',
      'Safari, Chrome …': 'Safari, Chrome …',
      '‹ Anderes Gerät wählen': '‹ Choose another device',
      'Automatisch einrichten per ADB': 'Set up automatically via ADB',
      'LoxPanel installiert Fully Kiosk und den „LoxPanel“-Launcher auf dem Gerät und trägt die Start-Adresse ein. Du musst nur am Gerät ADB über WLAN einschalten (Einstellungen → Entwickleroptionen → USB-Debugging / ADB über WLAN, Port 5555). Beim ersten Mal fragt das Gerät „USB-Debugging zulassen?“ – mit „Immer erlauben“ bestätigen und den Knopf noch einmal drücken.': 'LoxPanel installs Fully Kiosk and the “LoxPanel” launcher on the device and enters the start address. You only need to switch on ADB over Wi-Fi on the device (Settings → Developer options → USB debugging / ADB over Wi-Fi, port 5555). The first time, the device asks “Allow USB debugging?” – confirm with “Always allow” and press the button again.',
      'Gerätename': 'Device name',
      'IP-Adresse des Geräts': 'Device IP address',
      'Fully Kiosk ist schon auf dem Gerät – nur den Launcher einrichten': 'Fully Kiosk is already on the device – only set up the launcher',
      'Automatisch einrichten': 'Set up automatically',
      'Zu „Meine Geräte“': 'Go to “My devices”',
      'Gerätename, IP-Adresse und Server-Adresse nötig': 'Device name, IP address and server address required',
      'Lade Fully Kiosk und installiere per adb … (bis zu einer Minute)': 'Downloading Fully Kiosk and installing via adb … (up to a minute)',
      'Sobald das Gerät die Visu geöffnet hat, erscheint es unter „Meine Geräte“.': 'As soon as the device has opened the visu, it appears under “My devices”.',
      'Adresse für iPad, iPhone oder Browser': 'Address for iPad, iPhone or browser',
      'Alternativ: Start-URL von Hand eintragen': 'Alternatively: enter the start URL by hand',
      'Diese Adresse im Browser (Safari, Chrome …) öffnen. Mit „Zum Home-Bildschirm“ startet sie wie eine App. Der Gerätename sorgt dafür, dass das Gerät unter „Meine Geräte“ erscheint und per Betriebsmodus umgeschaltet werden kann.': 'Open this address in the browser (Safari, Chrome …). With “Add to Home Screen” it starts like an app. The device name makes the device appear under “My devices” and lets it be switched by operating mode.',
      'Status': 'Status',
      'Gerätetyp': 'Device type',
      'Ansicht': 'View',
      'Steuerung': 'Controls',
      'Wartung': 'Maintenance',
      'Einrichten per adb': 'Set up via adb',
      'Gerät offline': 'Device offline',
      'Gerät verbindet …': 'Device connecting …',
      '– die Knöpfe gehen wieder, sobald es erreichbar ist.': '– the buttons work again as soon as it is reachable.',
      'Zeile entfernt – wirksam mit Speichern': 'Row removed – takes effect on save',
      'Kalender „': 'Calendar “',
      '“ entfernt – wirksam mit Speichern': '” removed – takes effect on save',
      'Hintergrundbild entfernen?': 'Remove background image?',
      'Eigenen Klingelton entfernen? Danach gilt wieder der Standardton.': 'Remove custom ring tone? The default tone applies again.',
      'Wirkt sofort – nicht über „Speichern“': 'Takes effect immediately – not saved via “Save”',
      'Gerät offline – Steuerung nicht verfügbar': 'Device offline – controls not available',
      'Gerät verbindet – Steuerung gleich verfügbar': 'Device connecting – controls available shortly',
      'Weiteres': 'More',
      'Richtet Modus → Ansicht für mehrere Geräte auf einmal ein.': 'Sets up mode → view for several devices at once.',
      'Seite': 'Page',
      'Fläche links': 'Left half',
      'Fläche rechts': 'Right half',
      'So geht’s': 'How it works',
      'Passwortschutz entfernen? Danach kann jeder im Heimnetz diese Konfiguration öffnen.': 'Remove password protection? Anyone on the home network can then open this configuration.',
      'Eigene Farben dieser Vorlage zurücksetzen?': 'Reset custom colours of this template?',
      'Kachel auf Standard zurücksetzen?': 'Reset tile to default?',
      'Cover, Titel und Favoriten vom Loxone-Audioserver. Einen Test-Ton, um die Lautsprecher der Panels zu prüfen, findest du unter System → Diagnose.': 'Cover, title and favourites from the Loxone audio server. A test tone for checking the panel speakers is under System → Diagnostics.',
    }
  };

  function detect() {
    try { var s = localStorage.getItem('lp_ui_lang'); if (s && (s === 'de' || CAT[s])) return s; } catch (e) {}
    var n = (navigator.language || 'de').toLowerCase().split('-')[0];
    return (n === 'de' || CAT[n]) ? n : 'de';
  }

  var LANG = detect();

  function T(s) {
    if (s == null) return s;
    if (LANG === 'de') return s;
    var m = CAT[LANG];
    return (m && m[s] != null) ? m[s] : s;
  }

  function apply(root) {
    root = root || document;
    root.querySelectorAll('[data-i18n]').forEach(function (el) {
      var k = el.getAttribute('data-i18n') || el.textContent.trim();
      if (k) el.textContent = T(k);
    });
    root.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
      var k = el.getAttribute('data-i18n-ph') || el.getAttribute('placeholder') || '';
      if (k) el.setAttribute('placeholder', T(k));
    });
    root.querySelectorAll('[data-i18n-title]').forEach(function (el) {
      var k = el.getAttribute('data-i18n-title'); if (k) el.setAttribute('title', T(k));
    });
  }

  function mountSwitcher() {
    var host = document.querySelector('[data-langsel]');
    if (!host) return;
    var sel = document.createElement('select');
    sel.className = 'langsel';
    LANGS.forEach(function (l) {
      var o = document.createElement('option');
      o.value = l[0]; o.textContent = l[1];
      if (l[0] === LANG) o.selected = true;
      sel.appendChild(o);
    });
    sel.onchange = function () {
      try { localStorage.setItem('lp_ui_lang', sel.value); } catch (e) {}
      // Konfiguration: Sprache auch fuer Datum/Uhr der Panels uebernehmen, dann neu laden
      var p = (typeof window.syncPanelLang === 'function') ? window.syncPanelLang(sel.value) : null;
      Promise.resolve(p).then(function () { location.reload(); }, function () { location.reload(); });
    };
    host.appendChild(sel);
  }

  // ---- Auto-Uebersetzer fuer JS-generierte Seiten (z.B. /config) ----
  // Uebersetzt nur BLATT-Elemente (reiner Text, keine Kind-Elemente) der
  // angegebenen Chrome-Selektoren und nur, wenn es eine Uebersetzung gibt
  // (sonst bleibt der deutsche Text). Miniserver-Namen sind nicht im Katalog
  // -> bleiben unangetastet. Reagiert per MutationObserver auf Neu-Rendern.
  var _sel = null, _pending = false;

  function applyChrome(root) {
    if (!_sel) return;
    (root || document).querySelectorAll(_sel).forEach(function (el) {
      if (el.children.length) return;             // nur reine Textknoten
      var k = (el.textContent || '').trim();
      if (!k) return;
      var t = T(k);
      if (t !== k) el.textContent = t;            // nur bei echter Uebersetzung schreiben
    });
  }

  function _schedule() {
    if (_pending) return;
    _pending = true;
    var raf = window.requestAnimationFrame || function (f) { setTimeout(f, 16); };
    raf(function () { _pending = false; applyChrome(document); });
  }

  function autoChrome(selectors) {
    _sel = selectors;
    applyChrome(document);
    try {
      new MutationObserver(_schedule).observe(document.body,
        { childList: true, subtree: true, characterData: true });
    } catch (e) {}
  }

  // Global verfuegbar fuer die Seiten-Skripte (T fuer dynamisch erzeugte Texte).
  window.I18N = { lang: LANG, t: T, apply: apply, applyChrome: applyChrome,
                  autoChrome: autoChrome, langs: LANGS };
  window.T = T;

  document.addEventListener('DOMContentLoaded', function () {
    document.documentElement.setAttribute('lang', LANG);
    mountSwitcher();
    apply(document);
  });
})();
