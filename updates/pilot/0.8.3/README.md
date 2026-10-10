# Live Desk 0.8.3 — save browser during run recovery

0.8.2 blocked saving even an unchanged execution mode plus a browser connection choice when a recent run still needed review. The screenshot showed My running Chrome in the unsaved dropdown while the saved choice remained Separate Live Desk browser and Connect was disabled.

The fix permits browser-only saving on the local PC while automation is paused and no operation/recording is active. It changes only the browser choice. Execution mode, recipes, destinations, frozen program plans and the unresolved run journal remain intact. Mode or recipe changes still require recent runs to be resolved. No run is falsely marked reviewed, deleted, stopped or retried.

## Update and connect — no live action

1. Pause automation. Finish active live, recording and OBS replay normally before installing. Finish workflow recording too.
2. Updates → Open update controls → Check for updates → **0.8.3** → Download & install. Use the existing pilot feed; no folder deletion or new installation is needed.
3. After restart, open Visible automation. Choose **My running Chrome (existing login)**, then **Save browser only**. Execution mode can remain API. This button does not save an unsaved mode dropdown choice.
4. Confirm the status now says your running Chrome is selected and Connect my Chrome is enabled. Keep normal Chrome open with remote debugging allowed at `chrome://inspect/#remote-debugging`.
5. Click Connect my Chrome and accept Chrome's prompt only for the connection you requested. Then select Facebook preparation → Open site / sign in. Verify the official Page in the managed tab before any publishing action. Opening the page does not create a schedule, start a live or move the camera.

The previous run still requires separate inspection before changing workflows/mode or its protected destinations/program. Inspect the exact recorded events and OBS; do not delete or mark a live reviewed just to clear the warning.

The browser connection implementation and limitations from [0.8.2](../0.8.2/README.md) remain: explicit local permission, retained loopback WebSocket, no replacement browser launch or cookie copying, managed tabs, standard Windows stable Chrome debug marker and local reconnect after app/browser restart. Actual Windows permission and signed-in account acceptance still require a supervised PC check. Keep the existing YouTube Official Livestream key.

Pilot feed:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```
