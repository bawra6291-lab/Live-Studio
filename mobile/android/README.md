# Live Desk Mobile — Android LAN pilot 0.1.0

An installable Android 8.0+ companion for the existing Windows Live Desk. It opens
its paired operator dashboard: Enable/Pause automation, schedule editing, connection
checks and activity. All scheduling, streaming, saved credentials and camera work
continue on the PC. No Windows update or repeat YouTube/Facebook setup is needed.

## Install and connect

1. Keep the Windows Live Desk launcher running. Click **Enable mobile access** and
   note the phone address it shows (for example `http://192.168.29.247:8866`).
2. Install `Live-Desk-Mobile-0.1.0.apk` on an Android phone. If Android asks, allow
   installation from the browser/file manager you used for this file.
3. Connect the phone to the same trusted private Wi-Fi. Open **Live Desk Mobile**,
   enter the exact PC phone address, then tap **Connect to PC**.
4. Enter the pairing code from the Windows launcher (**Show code**). A newly
   paired device has the launcher's selected operator/viewer role. A viewer cannot
   enable automation. Codes expire after 30 minutes; the PC can generate a new one.
5. Review **Schedule**, then use **Enable automation** and its confirmation.
   **Pause automation** pauses future starts, automatic endings and camera steps;
   it does not end an existing live. Session expiry/revocation requires pairing again.

The app remembers its address and private pairing cookie. **Refresh** retries the
PC connection. **PC → Change PC** forgets the phone's pairing before entering a
new address; it does not change the old PC's schedule. Do not use the local PC
address `127.0.0.1:8865`. PC IP changes require entering the new mobile address.

## Boundaries

- Same private LAN only; no internet relay, PC power-on, Play Store or iPhone build.
- The PC must remain on with Live Desk running. Visible browser automation still
  needs its normal unlocked desktop, connected Chrome and reviewed workflows.
- Native chrome only navigates to the chosen RFC1918 IPv4 address on port 8866.
  Dashboard pairing, CSRF, role restrictions and offline handling are unchanged.
  Cleartext HTTP is limited in code to that origin; use trusted Wi-Fi, never expose
  port 8866 to the internet. No JavaScript bridge, file/content access or public
  site navigation is enabled. Credentials remain on Windows.
- Pilot signed with a temporary development certificate, not a production publisher
  key. Keep this APK. A future APK signed by a different key requires uninstalling
  the old phone app and pairing again; PC settings are unaffected. A production
  release needs a maintainer-held signing key and update channel. The key is never
  included in source, public artifacts or APK downloads.
- QA installs the APK in Android 15 and exercises the real dashboard against an
  isolated fake controller. It cannot prove this user's Wi-Fi, Windows firewall,
  device WebView version or actual livestream acceptance. No real live or camera
  command is sent during tests.

## Rebuild

JDK17, Android SDK platform35/build-tools35.0.0, `zip` and `sha256sum`:

```sh
bash mobile/android/test.sh
bash mobile/android/build.sh
```

For a maintainer-owned certificate, set `LIVE_DESK_KEYSTORE`, `LIVE_DESK_KEY_ALIAS`,
`LIVE_DESK_STORE_PASS` and `LIVE_DESK_KEY_PASS` in a private build environment.
The default pilot key is generated locally, kept in the ignored build directory
and excluded from CI uploads. The SDK's `apksigner verify` report and APK checksum
are emitted next to the APK. The workflow additionally runs an installed-app smoke
test. Its fixture refuses real services and other operations.
