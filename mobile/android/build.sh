#!/usr/bin/env bash
# Dependency-free native Android build with installed official SDK tools + JDK17.
set -euo pipefail
cd "$(dirname "$0")"
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
: "${SDK_DIR:?Set ANDROID_HOME to the Android SDK directory}"
TOOLS="$SDK_DIR/build-tools/35.0.0"
PLATFORM="$SDK_DIR/platforms/android-35/android.jar"
OUT="${1:-build}"
mkdir -p "$OUT/classes"
"$TOOLS/aapt2" compile --dir res -o "$OUT/resources.zip"
"$TOOLS/aapt2" link -I "$PLATFORM" --manifest AndroidManifest.xml --java "$OUT/generated" -o "$OUT/unsigned.apk" "$OUT/resources.zip"
find src "$OUT/generated" -name '*.java' -print > "$OUT/sources.txt"
javac --release 8 -classpath "$PLATFORM" -d "$OUT/classes" @"$OUT/sources.txt"
find "$OUT/classes" -name '*.class' -print > "$OUT/classes.txt"
"$TOOLS/d8" --lib "$PLATFORM" --min-api 26 --output "$OUT" @"$OUT/classes.txt"
(cd "$OUT" && zip -q unsigned.apk classes.dex)
"$TOOLS/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
# Pilot signing only. Private key remains temporary and is not uploaded or committed.
KEYSTORE="${LIVE_DESK_KEYSTORE:-$OUT/pilot.keystore}"
if [ -z "${LIVE_DESK_KEYSTORE:-}" ]; then
  export LIVE_DESK_STORE_PASS=android LIVE_DESK_KEY_PASS=android
fi
if [ ! -f "$KEYSTORE" ] && [ -z "${LIVE_DESK_KEYSTORE:-}" ]; then
  keytool -genkeypair -keystore "$KEYSTORE" -storepass android -keypass android -alias androiddebugkey -dname 'CN=Live Desk Development Pilot' -keyalg RSA -keysize 2048 -validity 3650 -noprompt
fi
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias "${LIVE_DESK_KEY_ALIAS:-androiddebugkey}" --ks-pass "env:LIVE_DESK_STORE_PASS" --key-pass "env:LIVE_DESK_KEY_PASS" --out "$OUT/Live-Desk-Mobile-0.1.0.apk" "$OUT/aligned.apk"
"$TOOLS/apksigner" verify --verbose --print-certs "$OUT/Live-Desk-Mobile-0.1.0.apk" > "$OUT/signature.txt"
"$TOOLS/aapt2" dump badging "$OUT/Live-Desk-Mobile-0.1.0.apk" > "$OUT/manifest.txt"
sha256sum "$OUT/Live-Desk-Mobile-0.1.0.apk" > "$OUT/SHA256SUMS"
