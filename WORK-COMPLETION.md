# Completion record — 0.8.2 pilot

This document distinguishes implemented software from external acceptance gates. It does not claim zero defects or production certification.

## Implemented in this increment

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
- Deploy the optional relay to an owned host/domain, obtain TLS, provision workspace access codes and enroll PCs. No hosted service, paid infrastructure or DNS changes have been created.
- Obtain Google/Meta production approval and configure public OAuth onboarding. The local app continues to use the current desktop OAuth JSON and Page-token setup; the relay is not an OAuth broker.
- Publisher code signing and authenticated release metadata require publisher credentials and protected CI configuration. Pilot artifacts are unsigned; no signing identity is invented.
- Independently review security, dependencies/licenses, load capacity and disaster recovery before a multi-customer production launch.

## Explicit product limits

This version supports IST, YouTube and Facebook together, a single workspace per Windows user and ISAPI camera patrols/presets. General IANA time zones/DST, YouTube-only/Facebook-only output plans, multiple concurrent workspaces on one PC, continuous manual PTZ joystick, other camera vendors, self-service email/SSO/billing, native OBS click recording, universal preconfigured site recipes and unattended Windows unlock are not implemented. They must not be advertised as complete. The configurable calendar and optional relay do not remove these limits.

## Delivery discipline

Keep stable main unchanged. Publish a pilot update only after this source revision passes Windows/Linux controller, relay authorization/queue, desktop/mobile browser, visible Chromium fixture and Windows installer checks. Record the exact source commit, workflow run and ZIP SHA-256 in the versioned pilot build report. A package checksum is integrity checking, not publisher signing.
