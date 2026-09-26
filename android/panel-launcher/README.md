# LoxPanel-Launcher (Android)

Mini-App für Wandpanels (z. B. Shelly Wall Display X2i): startet **Fully Kiosk**
beim Antippen des App-Symbols und automatisch nach jedem Neustart des Panels.
Ersetzt `adb shell monkey -p de.ozerov.fully -c android.intent.category.LAUNCHER 1`.

## Installieren

    adb connect 192.168.1.103:5555
    adb install -r LoxPanel-Launcher.apk

Einmal von Hand starten (aktiviert den Autostart nach dem Booten):

    adb shell am start -n de.loxpanel.launcher/.Main

## Optional: Panel-URL fest vorgeben

Ohne URL lädt Fully seine eigene Start-URL. Mit URL öffnet die App Fully direkt
mit dieser Adresse (einmalig setzen, wird gespeichert):

    adb shell am start -n de.loxpanel.launcher/.Main --es url "http://<LoxBerry-IP>:8098/?panel=wohnzimmer"

URL wieder entfernen: `--es url ""`.

## Falls der Autostart nicht greift (Android 10+)

Android blockiert dort App-Starts aus dem Hintergrund. Einmalig erlauben:

    adb shell appops set de.loxpanel.launcher SYSTEM_ALERT_WINDOW allow

## Bauen

    ./build.sh

Benötigt `aapt apksigner zipalign dalvik-exchange android-sdk-platform-23` und ein JDK.
Der Signaturschlüssel (`launcher.keystore`) entsteht beim ersten Build und liegt nicht
im Git. Wird mit einem anderen Schlüssel neu gebaut, vorher `adb uninstall de.loxpanel.launcher`.
