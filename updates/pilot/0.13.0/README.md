# Live Desk 0.13.0 — Automatic YouTube photo posting

DARSHANFLOW now includes a visible Chrome publisher for public YouTube Community photo posts. Individual Send and Send to all upload the reviewed 7/10 JPG images in order, enter the caption, dispatch Publish once, and save a newly observed matching post link. The manual YouTube link-entry box and manual photo handoff have been removed from the current UI. Existing manual reviews can explicitly create a new automatic draft; check for a previous manual publication before confirming it.

## Use the existing app and Chrome

1. In App updates, check and install 0.13.0 while idle.
2. DARSHANFLOW → Connections → Verify YouTube. Check the intended channel.
3. Chrome posting setup → My running Chrome → Save browser only → Connect my Chrome. In ordinary Chrome, enable Allow remote debugging at chrome://inspect/#remote-debugging if needed and approve its browser-control prompt. This uses the existing Chrome login, not another profile. The channel primary owner must be selected; YouTube Advanced account settings must show the intended channel ID.
4. Keep the Windows desktop unlocked. Arrange photos, review one destination or Send to all, and confirm Send. Watch the Chrome upload/publish and the returned link in posting history. No manual image upload, caption pasting or post-link pasting is required by this flow.

## Validation and limits

The production adapter was tested using actual Chromium/CDP file selection, input and mouse commands against local fixture pages, with nine positive/negative cases. The dashboard has 20 passing flows; controller suites have 307 unit tests and 24 remote tests. Windows native lifecycle and installer, Android companion and OBS layout checks pass. The updater stages 0.12.2 → 0.13.0 without a dependency upgrade. See build-report.json for source and validation identifiers.

**Real-account acceptance has not been performed.** No real YouTube account or post was used by these tests. The first actual publication needs a supervised check on the operator PC; support for a particular live YouTube DOM variant is not established by local fixtures. Unsupported layout/account states stop for review rather than guessing clicks. A dispatched or uncertain publish is never automatically repeated.

WhatsApp remains a separate manual share-sheet/destination step. Existing live settings, Official stream key and reference document are retained.
