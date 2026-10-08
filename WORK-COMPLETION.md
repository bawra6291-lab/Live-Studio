# Completion record — 0.8.5 pilot

This document distinguishes implemented software from external acceptance gates. It does not claim zero defects or production certification.

## Implemented in this increment

- 0.8.5 visible setup layout: group execution-mode selection with its Save action and browser selection with browser-only Save, connection status and Connect/Disconnect actions. Labels sit above full-width fields in setup, recording and review. Workflow selection has its own row, related platform IDs share the following row, and Chrome setup guidance is expandable. Setup cards stack in narrow windows; existing action IDs and save behavior remain intact. The existing dashboard flow captures owner-view screenshots at desktop and narrow widths and checks overflow.

- 0.8.4 recording-finish repair: opaque/blank-frame ready/skipped messages were origin-validated before being recognized as bookkeeping, causing the reported HTTP(S) address error and discarding the review draft. Filter those non-action messages first; real action origins are still validated and foreign-origin actions excluded. Regressions reproduce the old exception, retain valid identity/fill/click steps, reject an empty health-only session and refuse an opaque-origin action. The actual browser-socket fixture mixes opaque health messages with trusted input. The operator has now confirmed normal Chrome connection and signed-in Facebook navigation; complete site recipes remain unverified.

- 0.8.3 browser-only recovery fix: the unresolved-run guard previously blocked even a browser connection choice. Local browser-only saving is now allowed while idle and paused, with explicit preservation of execution mode, recipes, destinations and run journal. Changing mode/recipes remains guarded. The UI provides Save browser only and identifies an unsaved browser choice. HTTP tests reproduce the operator's blocked-save state and prove retained journal/settings, rejected mode/recipe mutations, and pause/local/confirmation boundaries.

- 0.8.2 normal Chrome connection: local browser choice, explicit Connect/Disconnect, Chrome-managed consent, one retained loopback browser WebSocket, flattened page sessions and one managed tab per service. Reads only standard stable Chrome's DevToolsActivePort marker; no HTTP discovery dependency or copying website/profile secrets. Rejects absent/denied/lost connection without a replacement launch or blind replay. Existing personal tabs and browser windows remain open. Connections are not restored automatically after app/browser restart. Actual Windows inspect permission and signed-in platform acceptance remains a supervised operator gate.

- 0.8.1 browser-session repair: reconnect to the browser identified by the persistent Live Desk profile before launching, reuse an existing same-site tab after a controller restart, refuse duplicate launch when the existing process is unresponsive, and prefer per-user Chrome over system Edge. Local Chromium regression checks the same target ID, unchanged tab count and retained test-site cookie/local storage through reattachment and recording. This does not attach to the normal default Chrome profile or guarantee that external sites never expire sessions.

- Calendar: daily, selected weekdays or a single date, skipped dates, 5–60 minute preparation lead, collision checks including overnight and far-future one-off runs, upcoming preparation/start/end preview. Existing IST daily plans remain compatible and frozen prepared plans remain unchanged.
- Recovery: persisted run history, exact recorded platform links, read-only inspection, fresh inactive-state check before marking reviewed, audit preservation and cancellation of remaining actions for reviewed runs. Explicit end for the recorded run reuses exact platform/output ownership checks; changed outputs refuse automatic stopping. No automatic deletion of ambiguous broadcasts.
- Portable settings backup/restore: validated schema and schedule, pre-restore backup, paused restore, existing credential namespace, secrets and journal preserved. No arbitrary executable path or network host can be injected by importing a backup.
- Connection recovery: bounded preflight retry; permanent YouTube HTTP/auth and Facebook token errors stop retrying and give actionable guidance. Old missed-run messages remain in history instead of replacing current connection status.
- LAN devices: operator/viewer roles, 30-minute new-device pairing codes, 12-hour sessions, local-only device list/revoke and code rotation. Viewer write denial is enforced by the server.
- Optional outbound HTTPS remote control: workspace-scoped devices/users, owner/operator/viewer authorization, enrollment/revocation, fresh heartbeat/boot binding, command expiry, nonce idempotency, single dispatch and durable PC receipt. Local automation is independent of relay/network uptime. Includes a separate mobile web console and Docker/Caddy deployment files.
- Windows installer: private CPython/Tk/dependencies beside the updater-managed app directory, per-user installation, shortcuts and uninstaller. Includes a relocated-runtime smoke check and CI silent install/uninstall. Existing ZIP updates and credentials are retained.

## Existing features retained

Both-platform scheduling, custom end times and camera actions, exact existing YouTube Official Livestream key matching, reference title/date/description/thumbnail reuse, OBS profile/collection checks, protected FB Live output updates, admin OBS setup, in-app ZIP rollback, local credentials, LAN dashboard, and opt-in calibrated visible-browser workflows. Visible actions still require actual-site calibration; they are not fabricated screen animations.

## External acceptance gates — not completed here

- Install/migrate on the actual operator PC, verify administrator OBS visibility, plugin output reload, visible YouTube/Facebook/camera recipes, real broadcast start/end, lock/sleep/wake behavior and camera physical motion. The operator reported API-mode live working on 7 October 2026. Visible-site calibration and the remaining PC/camera acceptance checks still need supervised verification. Automated platform tests use isolated fake services.
- The optional HTTPS relay is deployed at https://live-desk-relay-production.up.railway.app with separate owner/agent grants and a 500 MB persistent volume. Hosted TLS/auth/CSRF and session durability through container redeployment passed. Enrolling the actual PC and testing the actual phone cellular network remain with the operator. No payment plan was purchased.
- Obtain Google/Meta production approval and configure public OAuth onboarding. The local app continues to use the current desktop OAuth JSON and Page-token setup; the relay is not an OAuth broker.
- Windows publisher code signing and authenticated release metadata require publisher credentials and protected CI configuration. Windows pilot artifacts remain unsigned; Android 0.2.0 uses its privately backed-up permanent self-signed package signer.
- Independently review security, dependencies/licenses, load capacity and disaster recovery before a multi-customer production launch.

## Explicit product limits

This version supports IST, YouTube and Facebook together, a single workspace per Windows user and ISAPI camera patrols/presets. General IANA time zones/DST, YouTube-only/Facebook-only output plans, multiple concurrent workspaces on one PC, continuous manual PTZ joystick, other camera vendors, self-service email/SSO/billing, native OBS click recording, universal preconfigured site recipes and unattended Windows unlock are not implemented. They must not be advertised as complete. The configurable calendar and optional relay do not remove these limits.

## Delivery discipline

Keep stable main unchanged. Publish a pilot update only after this source revision passes Windows/Linux controller, relay authorization/queue, desktop/mobile browser, visible Chromium fixture and Windows installer checks. Record the exact source commit, workflow run and ZIP SHA-256 in the versioned pilot build report. A package checksum is integrity checking, not publisher signing.


## Android LAN companion pilot 0.1.0

An installable native Android client connects to the existing Windows Mobile access
address (private IPv4, HTTP port 8866). Its paired dashboard supports the existing
operator Enable/Pause, schedule and activity controls; settings and platform
credentials stay on the PC. No Windows package or account migration is needed.
The client remembers address/pairing, supplies Refresh and Change PC, constrains
WebView navigation/resources to the selected origin, disables file/content/bridge
access and backup, and leaves all role/CSRF/offline rules with the real dashboard.
Android 15 system/keyboard insets are handled. No public-site login is required.

Tested source c065112900c72b273526fffa92107f0e244172d4 passed Android validation
37703237621: private-address/origin tests, compiled and signed APK verification,
installed pairing/rejection, confirmation/cancel/Enable/Pause, remembered session,
offline disabled controls/recovery and changing PC without commanding the old PC.
All six installed-app checks used the real web dashboard and an isolated fake
controller; no engine, platforms or camera were invoked. Existing Windows/web
validation 37703237746 also passed. APK and checksum are in updates/mobile/pilot/0.1.0.

This is a LAN pilot for Android 8+ (device acceptance tested in Android 15 emulator),
not iPhone, internet remote control or PC power-on. The PC remains responsible for
actual streaming and visible workflows. Actual user's device/network acceptance,
production mobile publisher signing and a persistent mobile binary update channel
remain pending. The temporary pilot private key is not committed or distributed.


## Android 0.2.0 — internet controls and persistent updates

The Android companion now accepts the operator-selected trusted HTTPS relay origin as well as private LAN HTTP. Internet phone pairing is stored in relay SQLite, renewed on use, and independent for each phone. Normal app/PC/server restarts and same-signer app upgrades retain it; logout, Forget phone, grant revocation, app data deletion, lost relay data or a 365-day inactivity interval require pairing again. The PC keeps its separate outbound-HTTPS agent enrollment in Windows Credential Manager. Existing LAN sessions still use their older 12-hour policy. Internet screens expose Check/Enable/Pause and status/history/revocation; detailed schedule editing remains local/LAN.

Updates inside the installed app use a fixed official HTTPS feed, size/hash checks, exact package and strictly higher versionCode checks, and exact installed-signer matching. A private read-only content provider grants the Android installer only the verified APK. Android installation approval is required. Verified downloads can be resumed after granting Allow from this source. A persistent self-signed Android signing key and private relay enrollment setup backup have been saved privately outside the public repository. This is package continuity, not Windows publisher certification. The old temporary-signer 0.1.0 needs one initial replacement; new releases must retain the 0.2.0 signer.

Source ad2e0f0563e079652a9ebde60856cd9a7f2f0234 passed Android workflow 37721981796: nine installed native checks, including updater signer/version/package/downgrade rejection, restricted installer provider, retained pairing through an installed same-signer replacement, in-app HTTPS feed check, confirmation/Enable/Pause and reconnect. Twenty-two relay tests cover migration/durable sessions, tenant separation, phone revocation and queued-command cancellation, CSRF, heartbeat/boot guards, expiration, dispatch/receipt idempotency and disabled API before HTTPS origin configuration. Workflow 37721981795 passed Windows/Linux controllers, installer, desktop/mobile UI and the isolated HTTPS remote browser flow with restored phone login, command acknowledgements and revocation. No actual platform live or camera operation was invoked.

Released APK code/resources/manifest match the tested aligned APK byte-for-byte. The final APK has separately verified permanent signing, SHA-256 d50cbd0a8b631e6e4d31b9acdffa9ae3911e37af4ff2ee61d9d227c022b4a089, 29166 bytes. APK, reports and Hindi guide are under updates/mobile/pilot/0.2.0. Stable main remains unchanged.

The operator approved deployment and public HTTPS exposure on 8 October 2026. The relay now runs at https://live-desk-relay-production.up.railway.app using pinned source 9edce04918891b9aa7f69c19cda56e5bc19fad65 and a 500 MB persistent volume. Hosted checks passed: valid TLS, configured health, owner login, secure renewed cookie, distinct agent authorization, CSRF/Origin rejection, and existing phone session retained through container redeployment. Temporary QA login was logged out; the actual PC remained offline and no live/control command was queued. Private one-time PC/phone setup is saved outside the public repository. Actual PC enrollment and phone-cellular acceptance remain pending; see remote/DEPLOYMENT-REVIEW.md.
