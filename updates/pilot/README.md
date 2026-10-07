# Live Desk 0.8.5 — supervised pilot

This is an opt-in test build from the development branch. It is not the stable release or the finished cloud/team product. The stable `main/updates/latest.json` feed remains unchanged.

## New in 0.8.5: aligned visible setup controls

Execution mode and Chrome connection now have separate cards. Labels sit above full-width fields; Save actions sit under their selections; browser status and Connect/Disconnect controls stay together. Workflow and review fields follow the same aligned structure. Chrome setup guidance is expandable and the cards stack in narrow windows. Existing control behavior is retained. See [the 0.8.5 guide](0.8.5/README.md).

## Retained from 0.8.4: finish recording despite opaque-frame health events

The reported HTTP(S) address error is reproduced by a ready/skipped recorder message from a blank or opaque frame. Those bookkeeping messages are now filtered before validating real action origins, preserving valid captured steps. Empty recordings, opaque-origin actions and foreign destinations remain guarded. This does not add iframe replay support. See [the 0.8.4 guide](0.8.4/README.md).

After updating when OBS/live are idle, keep API mode and automation paused, reconnect normal Chrome and record one harmless Home click. Finish recording must display the captured step. No new public schedule/live is needed for that check; do not save a diagnostic click as a complete recipe. The older failed review draft cannot be recovered. Record preparation and Go live separately.

## Retained from 0.8.3: save browser while recovering a run

A recent unresolved run no longer blocks a browser-only choice. **Save browser only** preserves execution mode, recipes, destinations and the run journal while allowing local Chrome setup with automation paused. Mode/recipe changes still require run review. Unsaved browser choices are identified on screen. See [the 0.8.3 guide](0.8.3/README.md).

## Retained from 0.8.2: your running Chrome

Choose **My running Chrome (existing login)**, save the browser choice and connect locally. Chrome handles permission; one retained loopback browser WebSocket drives managed tabs in the already open browser. Missing/denied/lost connections refuse a replacement launch. Personal tabs are left alone, and no profile cookies are copied. Reconnect locally after Chrome/Live Desk restart. The operator has confirmed the normal Chrome connection and signed-in Facebook navigation; complete visible-site workflows remain a supervised PC gate. See [the 0.8.2 guide](0.8.2/README.md).

## Historical 0.8.1: persistent browser reuse

The visible adapter reconnects to the existing Live Desk browser before launching, reuses same-site tabs after an app restart, and prefers Chrome when installed. Sign in once per site in this persistent profile; Open site, recording and replay use the same browser session. Normal Chrome is separate, and site sessions may still expire. See [the 0.8.1 guide](0.8.1/README.md).

## New in 0.8.0

Calendar recurrence and preview, recorded-run recovery and targeted ending, credential-free settings backup/restore, LAN device roles/revocation, an optional self-hosted HTTPS relay, and a bundled Windows installer are implemented. See [the 0.8.0 guide](0.8.0/README.md) and [completion record](../../WORK-COMPLETION.md). The relay requires separate hosting and enrollment; internet access is off by default.

## Recorder repair retained from 0.7.1

A reported recording returned no steps. The previous recorder used the retargeted DOM element, which can miss controls inside open shadow roots; it also silently accepted an empty result. The recorder now follows the composed event path, listens inside dynamically discovered open shadow roots, captures simple identity text as a result check and excludes editable text from target labels. A LIVE DESK RECORDING badge shows the captured count on the current page. The count resets on navigation. Empty or oversized recordings fail explicitly; Save is disabled without captured steps. This repairs a tested capture gap; the exact cause of the operator's empty session cannot be established from a screenshot alone.

After updating while idle, leave automation paused. Open the old reference, start recording and check that the badge appears. Click a harmless existing control such as Dismiss, then Finish recording. Confirm that a step appears before attempting a full workflow. Do not create another public schedule for this diagnostic. An active live must finish before installing the update.

## New in 0.7.0: Visible browser workflows

Open **Visible automation** on the PC. This version includes a real recorder/replayer for reviewed, calibrated site workflows, with local-only setup, an isolated Chrome/Edge profile and no captured text-field values. API mode stays the default. Platform writes have a single browser owner in Visible mode; API reads verify results. OBS uses its existing WebSocket adapter with its real window.

Read [VISIBLE-MODE.txt](../../app/VISIBLE-MODE.txt) before recording: manual actions on the real sites can publish a live or move the camera. No real account/camera calibration or full live test has been performed by CI. Login/UAC, native dropdown/file upload, iframe/legacy plugin and unsupported entry-page flows require manual handling or a tested adapter. Do not enable unattended visible execution until calibration and supervised verification are complete.

## OBS administrator fix in 0.6.1

Windows Task Scheduler can return the principal as an account name even when setup registered a SID. Earlier builds compared the text directly and incorrectly rejected that valid task. The launcher now resolves the account through Windows and requires the resolved user SID to match the current process user. Unresolved accounts, other users, groups, noninteractive tasks and changed OBS actions remain rejected. Existing correctly configured administrator tasks do not need to be recreated. Windows CI exercises the native account-name lookup; actual OBS launch still requires the operator PC check.

## Existing app se update (PC par)

1. Agar live/recording chal rahi hai, pehle use normally finish karein. Automation **Pause** karein. OBS replay buffer bhi band ho. Live ke beech install na karein.
2. Live Desk → **Updates** → **Open update controls**.
3. **Online update address** mein ye URL paste karein:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```

4. **Check for updates**. New update source ka prompt aaye to URL check karke accept karein. **Version 0.8.5** aur **PILOT** notes dikhne chahiye.
5. **Download & install**. App restart hone dein. Folder ya shortcut manually delete/change na karein.
6. Restart ke baad installed version **0.8.5** confirm karein. Automation paused hi rakhein.

If no update appears, do not repeatedly install: capture the Updates panel message and installed version. If your existing app is already 0.8.5 or newer, this package will not be offered as an upgrade.

## Pehla check — koi live start nahi karna

1. **Connections** mein existing OBS profile, collection, scene, Facebook target and camera address check karein. Migrated ISKCON setup mein apni pehle se configured Facebook Page aur existing stream-key selection rehni chahiye. Legacy channel-ID field blank ho sakta hai; the existing reference ownership check is retained.
2. Stream key ke secret value ko reset ya replace na karein. OBS aur YouTube Studio mein wahi existing existing stream selected rahe.
3. **Check connections** click karein. This can open/show OBS, but it does not create/start a broadcast or move the camera.
4. **Activity** mein OBS, YouTube and Facebook verification dekhein. Camera actions configured hain to unki availability check hogi; no actions hone par camera check skipped dikhna sahi hai.
5. PC launcher ka **Open / Show OBS** click karke dekhein ki OBS window accessible hai. Administrator/task error aaye to exact text note karein; repeatedly rerun setup or start another OBS copy na karein.
6. **Export diagnostics** se result save karein, ya Activity ka screenshot bhejein. Tokens, passwords and stream keys screenshot mein na dikhayein.

A passed connection check does not prove real live start/end, UAC prompting, camera movement, locked-screen capture or recovery after sleep. Do not enable unattended daily starts until a supervised live test passes.

## Actual short live test — separately, when the operator is ready

- Keep the Windows launcher running and the PC awake/unlocked. Inspect OBS's program scene and audio first.
- Use a clearly named temporary program with a previous livestream reference from the same channel. Leave the regular daily program rows intact. Choose a start at least 10 minutes ahead and an end several minutes later; these broadcasts are public.
- Begin without camera steps to verify both platforms and automatic ending. Once that works, separately test an explicitly chosen, verified camera action while watching the camera and OBS.
- Save the test plan, then intentionally enable automation. Observe Activity during preparation (five minutes before start), verify both platform pages, and keep manual OBS/platform controls available.
- If a step fails or only one destination starts, inspect OBS and both platforms. Do not blindly retry or create more schedules. Export diagnostics.
- Remove the temporary program after its run has ended and been reviewed. Recheck daily timings before re-enabling regular automation.

## What is preserved

Legacy Windows settings and Credential Manager service are retained. The migration saves `settings.before-workspace-migration.json`, and the updater keeps a previous-app folder. Existing OBS profile, Page selection, schedule and the existing stream-key name are covered by tests. No valid existing credential is replaced by this pilot. Expired/revoked credentials can still require reconnecting.

Keep those backups until the PC test is complete. If rollback is needed after editing programs, review settings and any active/partial broadcasts first; switching the feed back alone does not downgrade the app.

## Build evidence

- Tested 0.8.5 source: `a5a59337c192fe59a461fec5a5a0b8bce8104bc7`.
- [Validation checks](https://github.com/bawra6291-lab/Live-Studio/actions/runs/37682188462) passed 178 app tests and 12 relay tests on each OS, nine browser/mobile flows, actual visible browser recording/replay, Windows native smoke and bundled installer build/install/uninstall.
- Owner setup fits 1440, 980, 390 and 320px viewports without page overflow. Desktop and 320px screenshots were visually reviewed. Existing save/remote boundaries remain tested.
- [0.8.5 build report](0.8.5/build-report.json): all 45 packaged app files match tested source. The 0.8.4 updater stages/swaps the package in a disposable fixture, preserving previous app, sibling runtime, settings and browser profile.
- Normal Chrome connection and signed-in Facebook navigation are operator-confirmed; complete site/camera recipes remain unverified. No operator data is packaged. Pilot is unsigned; hosting, production OAuth and publisher signing are external gates.
- Historical [0.8.4 evidence](0.8.4/build-report.json), [0.8.3 evidence](0.8.3/build-report.json), [0.8.2 evidence](0.8.2/build-report.json), [0.8.1 evidence](0.8.1/build-report.json) and [0.8.0 evidence](0.8.0/build-report.json) remain available.

Later pilot updates use this same opt-in address. Stable main remains unchanged until separately approved for production rollout.
