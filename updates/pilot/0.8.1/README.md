# 0.8.1 pilot — one persistent visible browser

The visible adapter reconnects to the browser identified by the existing Live Desk profile before launching a browser. It reuses the site's existing tab after a controller restart, keeps the profile across updates, and refuses duplicate launch when the old browser process is unresponsive. Chrome is preferred when installed, including per-user installations.

## Existing app se update

1. Finish any active live, recording or replay normally. Pause automation and finish the visible recording, if one is active.
2. Updates → Check for updates → Download & install, using the same pilot feed:
   `https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`
3. Verify installed version **0.8.1**. The existing Official stream selection, settings, credentials and Live Desk browser profile remain.
4. Visible automation → choose the workflow → Open site / sign in. Keep that browser open. Sign in once per site in this profile, not in a separately opened normal Chrome window.
5. Record my actions reuses the same site tab. Check the recording badge before taking real actions. After an app restart, the adapter reconnects to the still-open browser and rediscovers the site tab.

The normal default Chrome profile is separate and its cookies are not copied. Browser login and Google OAuth API authorization are different. External sites can expire or revoke sessions, so reauthorization is still possible. If the browser is unresponsive, close only the Live Desk browser normally and retry; do not delete its profile.

Workflow recording/calibration and account/result checks still apply. This repair does not enable visible mode or create/start/end a broadcast. OBS remains accessible in its real window and controlled through WebSocket, without native mouse-click recording. Actual Facebook/YouTube/camera acceptance testing remains supervised.

Exact source commit, CI results, archive digest and disposable upgrade checks are recorded in build-report.json. Stable main is unchanged; this is an unsigned pilot.
