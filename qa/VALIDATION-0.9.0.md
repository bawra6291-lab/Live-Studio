# Live Desk 0.9.0 pilot validation

Validated source: `737cce1b0c736e56b895c08c8c3e2fc666dd543c`.

- Development validation [37872557087](https://github.com/bawra6291-lab/Live-Studio/actions/runs/37872557087): success on Ubuntu/Windows, 195 controller tests (one platform-specific skip on Linux), 24 relay tests, native Windows task identity/Tk/notification icon registration and clean removal, dashboard browser flows, managed thumbnail upload through actual Chromium CDP, relay browser controls, Windows installer build/install/runtime relocation/uninstall.
- Android companion validation [37872557103](https://github.com/bawra6291-lab/Live-Studio/actions/runs/37872557103): success, installed pairing/control and retained-session upgrade checks. Existing Android package remains 0.2.0; relay UI updates in place.
- Archive: `updates/pilot/0.9.0/ISKCON-Live-Desk.zip`, 178498 bytes, SHA256 `4e06fe049e012cc3ea1dfb431f98ccbb6ac92cea64226e1a39ebe806b24fd9a7`. All 57 packaged source files match the validated Git tree; updater extraction/checksum validation passed for an upgrade from 0.8.6.
- Internet relay deployment `9544130f-b64b-485a-aa02-22ee14af1709`: terminal SUCCESS, pinned to the validated source; existing persistent pairing volume retained.

Tests use disposable fixture clients. No real broadcast, schedule, camera movement, OBS launch, UAC or operator-PC command was sent. Production visible-page calibration and a supervised dual-platform live test remain operator acceptance gates. OBS preview is sampled about every 15 seconds, platform reads about every minute. Existing Official stream key is reused, never created or rotated. In-app installation requires paused automation and inactive OBS outputs; saved credentials, content media and schedules remain in the operator data folder. This is a pilot feed update; stable main is unchanged.
