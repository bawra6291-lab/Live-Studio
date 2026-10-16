# Live Desk 0.12.2 — YouTube preview channel fix

Fixes **The destination changed after preview** when a verified YouTube channel has no separately configured channel ID. Preview, Send, Send to all and the handoff link now use the same frozen channel identity. Verify YouTube remembers the discovered channel without changing your live configuration or Official stream key. Actual channel changes still require a fresh preview.

Update the existing app through App updates. Then DARSHANFLOW → Connections → Verify YouTube. Confirm the channel, return to Publish → Posting history → Open preview and send that saved draft. If you intentionally changed channels, prepare a new review instead. YouTube Community photo publishing still finishes on YouTube.

Validated source: `cc5b81afee730223da05da4043774a533aa8c79b`. All workflows passed: 305 controller tests, 24 remote tests, 20 browser flows, Windows native lifecycle and installer, Android companion and OBS layout. No real posts or live/camera actions were performed. The updater stages 0.12.1 → 0.12.2 without modifying the current install. Package details and run identifiers are in build-report.json.
