# LoxPanel-Launcher (Android)

Eigener Startbildschirm für Wandpanels (z. B. Shelly Wall Display X2i) mit zwei
großen Symbolen:

- **LoxPanel** – startet Fully Kiosk (wie `adb shell monkey -p de.ozerov.fully …`)
- **Shelly** – öffnet die ursprüngliche Shelly-Oberfläche

Die Shelly-Oberfläche ist selbst der Startbildschirm des Geräts und hat kein
App-Menü; nachinstallierte Apps bekommen dort kein Symbol. Deshalb wird diese App
als Startbildschirm (HOME) gesetzt, die Shelly-Oberfläche bleibt installiert und
über das zweite Symbol erreichbar.

## Installieren

    adb connect 192.168.1.103:5555
    adb install -r LoxPanel-Launcher.apk
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
Der Signaturschlüssel (`launcher.keystore`) entsteht beim ersten Build und liegt nicht
im Git. Wird mit einem anderen Schlüssel neu gebaut, vorher `adb uninstall de.loxpanel.launcher`.
