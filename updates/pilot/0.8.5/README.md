# Live Desk 0.8.5 — arranged visible automation controls

The Visible automation setup now has two clear sections:

- **Automation mode:** execution-mode field with its Save action underneath.
- **Chrome connection:** browser field, browser-only Save, connection status and Connect/Disconnect controls together.

Labels sit above full-width fields. Workflow selection has a separate row, followed by the YouTube/Facebook reference fields. Review fields use the same aligned layout. The Chrome connection guide expands when needed. Cards stack in narrow windows; current save, recording and consent behavior is retained.

## Apply through the existing app

Pause automation and finish active live/OBS recording/replay normally before installing. Updates → Check for updates → **0.8.5** → Download & install. Use the existing pilot feed. Saved setup remains; this package also includes the [0.8.4 recorder repair](../0.8.4/README.md).

After restart, confirm 0.8.5 and refresh the dashboard once. Open Visible automation to see the arranged fields. Connect normal Chrome locally again if needed. Keep API mode during calibration; this layout update does not create schedules, save recordings or enable automation.

Pilot feed:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```

## Validation

[Source checks](https://github.com/bawra6291-lab/Live-Studio/actions/runs/37682188462) passed 178 app tests and 12 relay tests on Windows/Linux, nine browser/mobile flows, actual visible-browser transport/recording/replay, Windows native smoke and installer build/install/uninstall. The owner setup was checked for overflow at 1440, 980, 390 and 320px. Desktop and 320px screenshots were visually reviewed. Existing browser-only save still preserves an unsaved execution-mode choice; remote setup boundaries remain tested.

All 45 packaged app files match the tested source. The 0.8.4 updater stages/swaps this package in a disposable fixture, preserving previous app, sibling runtime, settings and browser profile. [Build report](build-report.json) records exact revision, checksum and installer artifact. Stable main is unchanged; complete real platform/camera recipes remain a separate operator acceptance gate.

