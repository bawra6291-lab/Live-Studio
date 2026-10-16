# Persistent Android signer and future updates

Public package: org.livedesk.mobile. Version 0.2.0 begins the persistent signing line.
Public signer certificate SHA-256: a4cedc315f39eb7d3093880ab037ea82f83bb0f140722f2b971a21c7f92807f9.

The owner-controlled private signing/enrollment backup is named Live-Desk-Private-Signing-and-Setup.zip and is stored privately outside this public repository. Do not regenerate or replace this signer for ordinary releases. The certificate is self-signed Android package identity, not Windows publisher certification. Never put the private key, password or relay access codes in source control, CI artifacts, a public feed, screenshots or logs.

For a new APK: increment versionCode and versionName; run native build, installed pairing/reconnect/in-place-upgrade tests, signer rejection/provider tests, remote session tests and HTTPS UI tests. Download the aligned unsigned APK and official SDK apksigner from that passing run. Re-sign locally with the saved private key (password via environment/file, never literal shell arguments), verify its certificate fingerprint and signature, then publish the signed APK under a new immutable versioned path and update updates/mobile/pilot/latest.json last. Keep historical APKs unchanged. CI fixture APKs have temporary private keys and must never replace a public signed release.

The feed uses version, version_code, apk_url, sha256 and size_bytes. Retain legacy url/size fields for old consumers. The APK updater verifies the incoming exact certificate against the installed app, package identity, size, SHA-256 and strictly newer versionCode before invoking Android installation. Android approval is required.

The 0.1.0 APK has a different, temporary CI certificate. It cannot receive 0.2.0 as an in-place update. An initial uninstall/replacement loses its local pairing. Future 0.2.x updates with this signer keep the app installation and pairing.
