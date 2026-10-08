# Live Desk 0.8.6 · desktop controls in the dashboard

Use Updates -> Check for updates -> Download & install on the PC.
Pause automation and finish active live/recording before installing.
Existing connections, schedules, browser profiles and internet enrollment remain.

Pilot feed (configure once):
`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

Normal launch opens the dashboard only. PC controls in the sidebar contains
OBS/admin setup, Windows startup, logs, recovery launcher and Quit Live Desk.
Local Wi-Fi access is in Mobile access. Closing the browser keeps automation
running. Reopen Live Desk to return to the same controller. Quit Live Desk
explicitly to stop future automation and phone controls; existing live continues.
If an old console remains after the first update restart, quit the app once and
reopen OPEN-LIVE-DESK.cmd. Explicit updates, OBS and UAC remain native windows.
OPEN-LIVE-DESK-DIAGNOSTICS.cmd intentionally opens a troubleshooting console.

Validation: 182 app tests on Windows/Linux; hidden Tk host and recovery on Windows;
10 desktop/mobile browser flows, including cancellation and close/reopen persistence;
Windows native compatibility and installer build/install/uninstall; visible and
remote browser regressions. Desktop and 650px screenshots reviewed.
See build-report.json for provenance. Actual operator PC and hardware acceptance
remain to be confirmed; no real live, camera or credentials were used by QA.
