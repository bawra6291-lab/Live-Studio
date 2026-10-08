Live Desk Pilot — v0.8.6

Extract the whole ZIP. Close the previous app. Open OPEN-LIVE-DESK.cmd.
Normal launch opens the dashboard only; the host runs in the background.
PC controls: OBS, Windows startup, logs, recovery launcher and Quit Live Desk.
Mobile access: enable local Wi-Fi access and generate a pairing code here.
Closing the browser does not stop automation. Open OPEN-LIVE-DESK.cmd again
to return to the same running controller. Use PC controls -> Quit Live Desk
to stop the background app. The recovery launcher opens only when requested
or when the default browser cannot open.
Troubleshooting: OPEN-LIVE-DESK-DIAGNOSTICS.cmd intentionally shows a console.
OBS, UAC and explicitly requested update controls still use their own windows.
If dependencies are missing: py -m pip install -r requirements.txt

NEW v0.5: In-app Updates panel, HTTPS feed check/download/install, offline ZIP
import, previous-version backup and recovery on a failed new-app startup.
The default update address points to bawra6291-lab/Live-Studio on GitHub.
Existing v0.5.0 users can paste that address once. See UPDATE-GUIDE.txt. Updates run only on the PC,
while automation is paused and OBS outputs are idle. App folder path stays fixed.

NEW v0.4: Open / Show OBS restores the main OBS window. No tray launch flag.
For administrator OBS, run SETUP-OBS-ADMIN.cmd once and approve Windows UAC
using the same Windows admin account. The on-demand Task Scheduler entry launches
only the installed Program Files OBS, interactively, with highest privileges.
It never starts/stops streaming itself, terminates OBS, or elevates the dashboard.
An already-running OBS is reused; close/reopen it only when idle to change privilege.
Use REMOVE-OBS-ADMIN.cmd to remove this optional task.
Windows must be logged in. Real Windows/UAC/window behavior still needs testing.

NEW: editable daily start/end times, enabled programs, overnight runs,
up to 8 camera actions per program (patrol start/stop or ordinary preset),
fixed clock timing or a delay after both platforms confirm live.
Start/end/camera scheduling can be edited from the paired phone on the same LAN.

Pause -> Schedule -> edit -> Save my schedule -> Overview -> Enable automation.
Blank end means manual ending. A configured end only affects the recorded run
started by this app. Changed OBS outputs require manual review.
Pause also pauses scheduled endings and camera actions.

NEW: preflight retries, dated activity, missed-run reasons, heartbeat and a
local diagnostic export. For the failed morning run: Activity -> Export diagnostics.
Send ISKCON-diagnostics.json for investigation. Its exact cause remains unverified.

Read START-HERE-HINDI.txt for full instructions, examples and limits.
Read VALIDATION.txt for checks performed and Windows/hardware checks still needed.

Existing saved Windows settings/credentials are preserved. No automatic end time
is added during migration. The old app.py entry point now opens this dashboard.
Phone access is local HTTP on a trusted private LAN, not internet remote access.
No EXE/APK is included. The existing Windows Python installation is reused.
