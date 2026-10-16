# 0.8.0 pilot

Existing installations can install this update through the **same pilot feed**:

`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

Pause automation and finish or manually take over any live/recording before installing. Open Updates → Check for updates → Download & install. Verify version 0.8.0 after restart. Stored credentials, schedules and the existing Official stream selection remain; run Check connections before re-enabling automation. No need to recreate YouTube/Facebook setup just because the code updated.

## What changed

- Daily, selected-weekday or one-date programs; skipped dates, 5–60-minute preparation lead and upcoming timing preview.
- Run history with recorded platform links, read-only inspection, explicit review and targeted end controls. Review does not delete drafts or stop a camera patrol.
- Portable settings backup/restore, preserving existing credentials and history.
- Expiring LAN pairing codes, operator/viewer access and paired-device revocation.
- Optional HTTPS relay code and local enrollment panel for internet remote control. It is off by default and requires separately deployed hosting/TLS. See `remote/README.md` in the repository.
- A bundled Windows installer build for fresh installations; current users can continue using in-app ZIP updates. The CI installer artifact is unsigned and expires on 19 October 2026; rebuild from the tested source for later use.

Source commit, complete test evidence, installer artifact link, archive hash and remaining acceptance gates are recorded in build-report.json. Stable main remains unchanged. Real operator-PC, live-platform, visible-site and camera tests are still pending; public OAuth onboarding and publisher signing are not claimed complete.
