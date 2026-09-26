# ISKCON Live Desk

Windows livestream automation for ISKCON Kolkata, with OBS controls, custom schedules, camera actions and in-app updates.

## Update an existing installation

If your app already has **Updates**, pause automation after finishing all live/recording outputs. Open **Updates > Open update controls** and enter this address once:

```text
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/main/updates/latest.json
```

Choose **Check for updates > Download & install**. Version 0.5.1 has this address built in. The updater preserves the installation path and reuses settings and credentials stored separately under the same Windows login. After restarting, run **Check connections**, then enable automation when ready.

Apps older than v0.5 need a one-time upgrade to gain the updater. See the package's UPDATE-GUIDE.txt.

## Source and releases

Source code is under `app/`. Versioned packages are under `updates/`; `updates/latest.json` is the permanent feed. No personal tokens, credentials or diagnostic logs belong in this repository.

See `app/VALIDATION.txt` for test results and limitations. Actual Windows administrator OBS launch and update/restart require a supervised test. This software does not establish that Facebook/YouTube tokens or live eligibility are valid.
