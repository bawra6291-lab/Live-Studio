# Live Desk 0.9.3 — Windows taskbar branding

This update gives the desktop viewer and recovery host the stable Windows identity `ISKCON.LiveDesk.Desktop`. It replaces the old L-only ICO with multiple sizes rendered from the dashboard's existing lotus SVG. Installer shortcuts use the same identity. Window pinning uses the Live Desk icon, name and host entry point, never the private viewer process.

## Install from the existing app
1. When live, recording and replay buffer are finished, pause automation.
2. Open **Updates → Open update controls → Check for updates**.
3. Confirm **0.9.3**, then **Download & install**. Let Live Desk restart.
4. Open the desktop window. Check the lotus icon on the title bar and Windows taskbar.
5. If an old pinned Python icon remains, unpin that old item and pin the newly opened Live Desk window. Pinning does not replace or reset account settings.

Use the same pilot feed:
`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

The optional desktop renderer setup from 0.9.2 is reused. Connections, schedules, the selected Official YouTube stream key and controller behavior are unchanged.

## Validation
Source: `6683d221c0f6a741a1f9f83d8a029d431bbff78e`.
[Development validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38350949810) passed Windows/Linux controller tests, dashboard checks and Windows installer build/install/uninstall.
The real Windows WebView2 fixture verified the native window's AppUserModelID, relaunch icon/name/command and native icon handle. Reopening, minimizing/restoring, pairing rotation and closing without stopping the host also passed.
The 0.9.2 updater accepts this package with unchanged core dependencies. All 68 packaged source files match the validated public source. No real streaming account, OBS or camera was contacted in the fixture.

This is an unsigned pilot. The operator's existing Windows taskbar pin cache still requires checking on their PC.
