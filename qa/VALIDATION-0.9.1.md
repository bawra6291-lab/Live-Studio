# Live Desk 0.9.1: OBS dock layout preservation

Enabling automation used to maximize OBS, and the idle Facebook output profile reload could recreate the YouTube dock and move other panels. Open / Show OBS now preserves the current window size. A small OBS 32 Windows x64 helper captures and restores Qt dock positions, sizes, visibility and the dock lock around the existing idle profile reload.

The YouTube Official Livestream key, service settings, scenes and platform credentials are unchanged. The helper exposes only status, capture and restore through a fixed local request file; it cannot start/stop streams or control cameras.

## Operator setup

1. Install 0.9.1 through the existing pilot App updates feed.
2. Pause automation, finish live/recording/replay outputs and close OBS normally.
3. On the PC open This PC → Set up OBS layout protection; approve Windows UAC for the fixed Program Files installation.
4. Open / Show OBS, arrange the wanted layout, hide unwanted panels, and run Check connections.
5. Perform a supervised scheduled test before relying on unattended operation.

Setup supports standard Program Files Windows x64 OBS 32. It refuses to install while OBS is running and never kills/restarts OBS itself. Check connections blocks automation preparation if the helper is missing or its state restore cannot be confirmed.

## Validation

Validated application source: 3450f2c3945af7c87441362160aecd627af44bd3.
Native source: dadbab2ad85b8cf68369f6bf10f6421e7dd6021e.
Native DLL SHA256: 2ed65d8f7273171511369dc594b6a1eefc141d30aa6a14801bbe6f9a9a15054d.

- 204 application unit tests passed locally; Linux skips the Windows-only installer test.
- 24 relay regression tests passed; the relay was not changed or redeployed.
- Development validation succeeded on the integrated application: Windows/Linux controller, Chromium dashboard and Windows installation/uninstallation.
- Android companion validation succeeded; this PC fix requires no companion APK reinstall.
- Windows native build and actual Qt window fixture passed. The release DLL loaded, and simulated dock deletion/recreation restored positions, sizes, visibility, lock state and unchanged window geometry. Invalid, replayed, expired and unsupported commands were rejected.
- All 62 package source files exactly match public validated commit 3450f2c3945af7c87441362160aecd627af44bd3; the only additional file is the generated release hash manifest.
- ZIP SHA256: 9e527333d7c665eea863469606a74d657eb3c0aa782a0662146135c601e10e7c; size 205085 bytes.

CI: https://github.com/bawra6291-lab/Live-Studio/actions/runs/38008461911
Native fixture: https://github.com/bawra6291-lab/Live-Studio/actions/runs/38008282905
Android: https://github.com/bawra6291-lab/Live-Studio/actions/runs/38008461944

Real operator-PC OBS startup/UAC and an actual scheduled stream remain supervised checks. No real live, camera or user's OBS was operated during validation. The prior crash warning has no diagnosed cause and is not claimed fixed by this layout change.
