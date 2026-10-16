# Live Desk 0.8.4 — recording finish repair

The recorder received blank/opaque-frame ready or skipped health messages and tried to validate their address before recognizing that they were not replayable actions. This reproduced the reported “Visible browser address must be an HTTP(S) address without credentials” error and left the review list empty.

0.8.4 filters bookkeeping first and retains the allowed site's identity, text-field and click steps. Real action origins remain validated; foreign-origin actions remain excluded. A health-only session still fails as empty, and an action from an opaque origin still refuses the recording. This repair does not add iframe, file-upload or native-dropdown replay support.

## Update using the existing installation

1. Pause automation. Finish an active live and OBS recording/replay normally before installing. Do not install during a broadcast.
2. Updates → Open update controls → Check for updates → **0.8.4** → Download & install. Use the same pilot feed. Saved connections, schedules and browser profile remain.
3. After restart, keep API mode and automation paused. Open normal Chrome, then Visible automation → Connect my Chrome; accept only the requested local Chrome permission.
4. Select Facebook — create live event → Record my actions. Use only the tab with LIVE DESK RECORDING.
5. Click **Home** once and confirm the captured count increases. Then Finish recording. One harmless click must appear in the review list.
6. Do not save this diagnostic as a complete workflow, and do not create another schedule or live just to check the repair.

The older failed finish discarded its in-memory review draft; this update cannot recover those old clicks. Record and review a complete workflow later. Preparation and Go live must be separate recordings: never retain a Go live click in the preparation recipe. OBS native clicks are not browser-recorded. Preserve the existing YouTube Official Livestream key.

The operator has confirmed normal Chrome connection and signed-in Facebook navigation. This does not prove that full visible scheduling/start/end/camera recipes work on the real sites. Facebook preparation must produce an unpublished manual-Go-live draft; automatic publishing before OBS starts remains rejected.

Pilot feed:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```

## Evidence

[Source validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/37680302859) passed 178 app tests and 12 relay/agent tests on both Windows and Linux, nine dashboard/mobile flows, real Chromium recording/replay including opaque health events through the browser socket, Windows native smoke and bundled installer build/install/uninstall. All 45 packaged app files match that tested source. The 0.8.3 updater stages/swaps this package while preserving the previous app, sibling runtime, operator settings and browser profile in a disposable fixture.

See [build-report.json](build-report.json) for source revision, archive checksum and installer artifact. Pilot artifacts remain unsigned; stable main is unchanged.

