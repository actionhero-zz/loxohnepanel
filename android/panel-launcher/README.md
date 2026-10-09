# LoxPanel-Launcher (Android)

Eigener Startbildschirm für Wandpanels (z. B. Shelly Wall Display X2i) mit zwei
großen Symbolen:

- **LoxPanel** – startet Fully Kiosk (wie `adb shell monkey -p de.ozerov.fully …`)
- **Shelly** – öffnet die ursprüngliche Shelly-Oberfläche

Die Shelly-Oberfläche ist selbst der Startbildschirm des Geräts und hat kein
App-Menü; nachinstallierte Apps bekommen dort kein Symbol. Deshalb wird diese App
als Startbildschirm (HOME) gesetzt, die Shelly-Oberfläche bleibt installiert und
über das zweite Symbol erreichbar.

## Verhalten

- **Autostart:** Erscheint der Startbildschirm (nach dem Booten, nach einem
  Fully-Absturz oder wenn man Fully verlässt), startet LoxPanel nach 10 s von
  selbst. Ein dezenter Countdown zeigt das an; **jeder Tipp bricht ab** – so
  bleibt die Shelly-Oberfläche erreichbar.
- **Fully läuft schon:** Das LoxPanel-Symbol holt Fully nur nach vorn, die Seite
  wird nicht neu geladen. Nur wenn Fully nicht läuft, öffnet es die Panel-URL.
  Erkannt wird das bis Android 7 über die laufenden Dienste, ab Android 8 über
  die Nutzungsstatistik (Recht setzt die Einrichtung per
  `appops set de.loxpanel.launcher GET_USAGE_STATS allow`). Ohne dieses Recht
  lädt das Symbol wie früher immer die URL. Nach einem Fully-Absturz startet
  Fully mit seiner eigenen Start-URL – dort am besten dieselbe Panel-URL
  eintragen.
- **Design** wie das LoxPanel-Theme „Bunt“.

## Installieren per Klick (empfohlen)

LoxBerry → Plugin „LoxPanel Favoriten“ → **Android-Panel einrichten**: Panel-IP
eingeben, Profil wählen, „Launcher installieren & einrichten“. Das erledigt alle
Schritte unten automatisch (inkl. LoxBerry-Adresse als URL). Ist auf dem Panel
schon dieselbe oder eine neuere Launcher-Version installiert, wird das
Installieren übersprungen.

## Installieren von Hand

    adb connect 192.168.1.103:5555
    adb install -r config/app/android/LoxPanel-Launcher.apk
    adb shell cmd package set-home-activity de.loxpanel.launcher/.Home
    adb shell appops set de.loxpanel.launcher GET_USAGE_STATS allow
    adb shell input keyevent 3        # Home-Taste: neuer Startbildschirm erscheint

Fragt Android beim ersten Home-Tippen nach dem Startbildschirm: „LoxPanel“ → „Immer“.

## Rückgängig machen

    adb uninstall de.loxpanel.launcher

Danach ist die Shelly-Oberfläche wieder der Startbildschirm.

## Optional: Panel-URL fest vorgeben

Ohne URL lädt Fully seine eigene Start-URL. Mit URL öffnet das LoxPanel-Symbol
Fully direkt mit dieser Adresse (einmalig setzen, wird gespeichert):

    adb shell am start -n de.loxpanel.launcher/.Main --es url "http://<LoxBerry-IP>:8098/?panel=wohnzimmer"

URL wieder entfernen: `--es url ""`.

## Bauen

    ./build.sh

Benötigt `aapt apksigner zipalign dalvik-exchange android-sdk-platform-23` und ein JDK.
Die APK landet in `config/app/android/` (von dort installiert sie der Server),
daneben `LoxPanel-Launcher.version` mit dem `versionCode` für den Versionsvergleich.
Bei Änderungen `versionCode`/`versionName` im Manifest erhöhen. `targetSdkVersion`
bleibt ≥ 24 – Android 15 verweigert ältere Apps bei der Installation.
Der Signaturschlüssel `launcher.keystore` liegt bewusst im Repo: Updates per
`adb install -r` gehen nur mit demselben Schlüssel.
