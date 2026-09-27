# LoxPanel-Launcher (Android)

Eigener Startbildschirm für Wandpanels (z. B. Shelly Wall Display X2i) mit zwei
großen Symbolen:

- **LoxPanel** – startet Fully Kiosk (wie `adb shell monkey -p de.ozerov.fully …`)
- **Shelly** – öffnet die ursprüngliche Shelly-Oberfläche

Die Shelly-Oberfläche ist selbst der Startbildschirm des Geräts und hat kein
App-Menü; nachinstallierte Apps bekommen dort kein Symbol. Deshalb wird diese App
als Startbildschirm (HOME) gesetzt, die Shelly-Oberfläche bleibt installiert und
über das zweite Symbol erreichbar.

## Installieren per Klick (empfohlen)

LoxBerry → Plugin „LoxPanel Favoriten“ → **Android-Panel einrichten**: Panel-IP
eingeben, Profil wählen, „Launcher installieren & einrichten“. Das erledigt alle
Schritte unten automatisch (inkl. LoxBerry-Adresse als URL).

## Installieren von Hand

    adb connect 192.168.1.103:5555
    adb install -r config/app/android/LoxPanel-Launcher.apk
    adb shell cmd package set-home-activity de.loxpanel.launcher/.Home
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
Die APK landet in `config/app/android/` (von dort installiert sie der Server).
Der Signaturschlüssel `launcher.keystore` liegt bewusst im Repo: Updates per
`adb install -r` gehen nur mit demselben Schlüssel.
