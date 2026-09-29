# Live Desk 0.6.1 — supervised pilot

This is an opt-in test build from the development branch. It is not the stable release or the finished cloud/team product. The stable `main/updates/latest.json` feed remains unchanged.

## OBS administrator fix in 0.6.1

Windows Task Scheduler can return the principal as an account name even when setup registered a SID. Earlier builds compared the text directly and incorrectly rejected that valid task. The launcher now resolves the account through Windows and requires the resolved user SID to match the current process user. Unresolved accounts, other users, groups, noninteractive tasks and changed OBS actions remain rejected. Existing correctly configured administrator tasks do not need to be recreated. Windows CI exercises the native account-name lookup; actual OBS launch still requires the operator PC check.

## Existing app se update (PC par)

1. Agar live/recording chal rahi hai, pehle use normally finish karein. Automation **Pause** karein. OBS replay buffer bhi band ho. Live ke beech install na karein.
2. Live Desk → **Updates** → **Open update controls**.
3. **Online update address** mein ye URL paste karein:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```

4. **Check for updates**. New update source ka prompt aaye to URL check karke accept karein. **Version 0.6.1** aur **PILOT** notes dikhne chahiye.
5. **Download & install**. App restart hone dein. Folder ya shortcut manually delete/change na karein.
6. Restart ke baad installed version **0.6.1** confirm karein. Automation paused hi rakhein.

If no update appears, do not repeatedly install: capture the Updates panel message and installed version. If your existing app is already 0.6.1 or newer, this package will not be offered as an upgrade.

## Pehla check — koi live start nahi karna

1. **Connections** mein existing OBS profile, collection, scene, Facebook target and camera address check karein. Migrated ISKCON setup mein Facebook Page `113962385367196` aur stream key name **YouTube Official Livestream** rehna chahiye. Legacy channel-ID field blank ho sakta hai; the existing reference ownership check is retained.
2. Stream key ke secret value ko reset ya replace na karein. OBS aur YouTube Studio mein wahi existing Official stream selected rahe.
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

Legacy Windows settings and Credential Manager service are retained. The migration saves `settings.before-workspace-migration.json`, and the updater keeps a previous-app folder. Existing OBS profile, Page selection, schedule and the Official stream-key name are covered by tests. No valid existing credential is replaced by this pilot. Expired/revoked credentials can still require reconnecting.

Keep those backups until the PC test is complete. If rollback is needed after editing programs, review settings and any active/partial broadcasts first; switching the feed back alone does not downgrade the app.

## Build evidence

- Source: `e4fe44467ed611c989a144e35df27d2a012fa854`.
- [Passing Windows/Linux/browser checks](https://github.com/bawra6291-lab/Live-Studio/actions/runs/36501063046): 130 controller tests on each OS, Windows native smoke check, seven desktop/mobile browser flows with fake services.
- `0.6.1/build-report.json` records the package digest, exact source match and a temporary-directory upgrade simulation from 0.5.5. It does not claim a real Windows installer handoff or real platform testing.
- Package contents include no operator settings, logs or credentials. Checksums detect corruption; this is not a signed production installer.

Later pilot updates can use the same opt-in address. Moving to a public/stable release remains a separate decision after the supervised PC test.
