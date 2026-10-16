# Live Desk 0.14.2 — YouTube image upload and photo verification

The previous adapter could select an already-present hidden input without activating YouTube Image mode. It also counted global image-picker previews as attached post photos and verified a published receipt using caption/author/link without a photo count.

This release explicitly activates Image before setting reviewed files. It waits for the picker Done button when processing is incomplete, checks that all photos are committed to the composer after the picker closes, waits for visible upload progress to finish, and rechecks the Chrome account before Publish. Selected file order remains checked. Success requires a new post link, expected author/caption, and the reviewed photo count. A text-only, incomplete or uncertain published post is retained for inspection, never automatically repeated.

Update through Live Desk → Updates → Check for updates → Download & install when no live or recording is active and automation is paused. Verify installed version 0.14.2. Inspect any prior YouTube post, then prepare a fresh preview and press Send to YouTube once. Keep Chrome open and the desktop unlocked; do not click YouTube Post manually while automation is running.

Validation: 317 controller tests on Windows/Linux; 24 remote controller tests; 21 dashboard flows; 27 actual local Chromium/CDP adapter cases; Windows native lifecycle and installer/runtime/uninstall; OBS helper validation passed. Cases include 7/10 ordered images, required Image activation, delayed Done, busy uploads, missing previews, discarded picker images, wrong account, changed caption/order, and missing/incomplete published attachments. Update staging from 0.14.1 passed; 102 payload files match the tested source; no dependency change.

Android APK build and static/remote tests passed, but the emulator could not launch because the SDK system-image download was not a valid ZIP. No Android source or APK is changed by this desktop update.

Tests use isolated local fixtures, not real accounts. The user's screenshot confirms selected photos and a text-only published post while app history is still uploading; it does not identify who clicked Publish. Real Chrome acceptance remains pending. No external posts were created or deleted during development. The original supplied studio document is unchanged.
