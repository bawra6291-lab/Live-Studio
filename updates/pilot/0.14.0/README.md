# Live Desk 0.14.0 — daily darshan workflow

Additions adapted from the supplied daily automation design into the existing app:

- Publish → Daily workflow: six saved caption templates, date variables and expanded preview.
- Local read-only pre-test for saved drafts: media hashes, target, service date, audio requirement, busy/live state, and draft fingerprint. Last checked account status is separate from a real authorization/publish test.
- Optional Telegram Facebook mixed sequence, positions 1–10 then 11–17; legacy 7+10 remains available. Frozen sequence metadata survives history reload.
- Required saved Instagram audio reference: new drafts are held before API sending and never silently sent without the requested audio. Native track attachment is not implemented.
- WhatsApp → RGM → JBS: saved L1 photo with date/links, then L5 photo, separate confirmations for 8 communities and the channel. JBS requires that destination's RGM confirmation; undo and edits invalidate related confirmations.

Existing app update: pause automation and finish any stream/recording, then Updates → Check for updates → Download & install. Saved connections and schedules remain outside the program folder. After restart verify Installed version 0.14.0.

317 controller tests on Windows/Linux, 24 remote controller tests, 21 dashboard flows and 9 local Chromium/CDP adapter cases passed. Windows native host lifecycle and installer/runtime/uninstall passed. These use isolated fixtures and do not prove real social account posting.

The previous YouTube Chrome channel-check failure still needs inspection of its actual Chrome tab. This release does not claim to fix it. WhatsApp remains assisted sharing. Scheduled/automatic-daily publishing, crop operations, native saved-audio sync and simulated retry/success controls from the HTML prototype are not imported as working capabilities.

The supplied original studio document remains byte-for-byte unchanged. No real posts, messages, live sessions, OBS or camera operations were performed for testing.
