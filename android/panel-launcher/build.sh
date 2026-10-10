#!/bin/bash
# Baut LoxPanel-Launcher.apk ohne Gradle/Android Studio.
# Benoetigt: apt install aapt apksigner zipalign default-jdk, dazu android.jar (API 28)
# und r8.jar (D8). Auf claude-pi liegen beide in ~/projekte/tools/android.
set -euo pipefail
cd "$(dirname "$0")"
TOOLS=${TOOLS:-$HOME/projekte/tools/android}
ANDROID_JAR=${ANDROID_JAR:-$TOOLS/p28/android.jar}   # API 28: TbView nutzt APIs ab 26 (zur Laufzeit geprueft)
R8_JAR=${R8_JAR:-$TOOLS/r8.jar}
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
# Java -> Bytecode (Java 8) -> classes.dex (D8 aus r8.jar; dx/alte d8 stuerzen bei javac 21 ab)
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -classpath "$ANDROID_JAR" -Xlint:-options \
      -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')
java -cp "$R8_JAR" com.android.tools.r8.D8 --release --min-api 19 --lib "$ANDROID_JAR" --output "$OUT" $(find "$OUT/classes" -name '*.class')
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
# versionCode daneben ablegen: der Server ueberspringt "adb install", wenn das
# Panel diese oder eine neuere Version schon hat.
sed -n 's/.*android:versionCode="\([0-9]*\)".*/\1/p' AndroidManifest.xml > "${DEST%.apk}.version"
