#!/bin/bash
# Baut LoxPanel-Launcher.apk ohne Gradle/Android Studio.
# Benoetigt (Debian/Ubuntu): apt install aapt apksigner zipalign dalvik-exchange
#                            android-sdk-platform-23 default-jdk
set -euo pipefail
cd "$(dirname "$0")"
ANDROID_JAR=${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}
# Schluessel liegt bewusst im Git: Updates per "adb install -r" gehen nur mit
# DEMSELBEN Schluessel. Er signiert nur diese Sideload-App (kein Store-Konto).
KEYSTORE=${KEYSTORE:-launcher.keystore}
# Fertige APK liegt im App-Ordner des Plugins -> landet im Docker-Image, der
# Server installiert sie von dort per adb auf die Panels.
DEST=../../config/app/android/LoxPanel-Launcher.apk
OUT=build
rm -rf "$OUT" && mkdir -p "$OUT/classes" "$OUT/gen" "$(dirname "$DEST")"

# Ressourcen + Manifest -> R.java und unsigniertes APK
aapt package -f -m -J "$OUT/gen" -M AndroidManifest.xml -S res -I "$ANDROID_JAR" -F "$OUT/unsigned.apk"
# Java -> Bytecode (Java 8, fuer dx) -> classes.dex
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -classpath "$ANDROID_JAR" -Xlint:-options \
      -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')
dalvik-exchange --dex --output="$OUT/classes.dex" "$OUT/classes"
(cd "$OUT" && aapt add unsigned.apk classes.dex > /dev/null)

# Signieren (Schluessel wird beim ersten Build erzeugt)
if [ ! -f "$KEYSTORE" ]; then
  keytool -genkeypair -keystore "$KEYSTORE" -storepass loxpanel -keypass loxpanel -alias launcher \
          -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=LoxPanel Launcher" > /dev/null 2>&1
fi
zipalign -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
apksigner sign --ks "$KEYSTORE" --ks-pass pass:loxpanel --key-pass pass:loxpanel \
               --v4-signing-enabled false --out "$DEST" "$OUT/aligned.apk"
apksigner verify "$DEST" && echo "OK: $DEST"
