#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
TOOLS="$SDK_DIR/build-tools/35.0.0"
PLATFORM="$SDK_DIR/platforms/android-35/android.jar"
OUT=build-instrumentation
mkdir -p "$OUT/classes" "$OUT/assets"
cp build-next/Live-Desk-Mobile-0.2.1-qa.apk "$OUT/assets/next.apk"
cp build-foreign/Live-Desk-Mobile-0.2.1-qa.apk "$OUT/assets/foreign.apk"
cat > "$OUT/AndroidManifest.xml" <<'MANIFEST'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.livedesk.mobile.qa" android:versionCode="1" android:versionName="qa">
<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>
<application android:label="Live Desk CI tests"/>
<instrumentation android:name=".UpgradeTest" android:targetPackage="org.livedesk.mobile"/>
</manifest>
MANIFEST
"$TOOLS/aapt2" link -I "$PLATFORM" --manifest "$OUT/AndroidManifest.xml" -A "$OUT/assets" -o "$OUT/unsigned.apk"
javac --release 8 -classpath "$PLATFORM:build/classes" -d "$OUT/classes" qa/UpgradeTest.java
find "$OUT/classes" -name '*.class' -print > "$OUT/classes.txt"
"$TOOLS/d8" --lib "$PLATFORM" --min-api 26 --output "$OUT" @"$OUT/classes.txt"
(cd "$OUT" && zip -q unsigned.apk classes.dex)
"$TOOLS/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$TOOLS/apksigner" sign --ks build/pilot.keystore --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out build/Live-Desk-QA.apk "$OUT/aligned.apk"
