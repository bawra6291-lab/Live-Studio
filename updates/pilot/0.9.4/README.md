# Live Desk 0.9.4 — compact Schedule

## Changes
- Programs appear as compact summaries with start/end time, repeat pattern, enabled status and camera-step count.
- Open one program at a time. Timings, Camera steps and Title & reference have separate accessible tabs.
- Camera actions use numbered expandable rows. Editing one action does not discard another action's fields.
- A sticky Save bar displays saved/unsaved state. Add/remove, save confirmation, discard, polling and hidden-field validation retain existing behavior.
- Upcoming runs, recorded runs and recovery are folded by default.
- Local SVG icons and responsive spacing improve navigation and schedule controls. No icon CDN or additional dependency is required.

## Update in the existing app
Finish active live/recording/replay, pause automation, then open **Updates → Check for updates → Download & install**. Confirm version **0.9.4** after restart. The same pilot feed is retained.

Click a program row, choose a tab, make changes and **Save my schedule**. Saving alone does not enable automation. Pausing automation also pauses scheduled endings and camera steps, as before.

Saved connections, descriptions, thumbnails, schedules, the existing Official YouTube stream-key selection and automation logic are preserved.

## Evidence
Validated source: `465df0b923e648d882ec8f6f0a15784da26f883d`.
[Development validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38354276081) passed: Windows/Linux controller, dashboard browser flows and bundled Windows installer.
The browser fixture checked four collapsed programs under 420px, eight camera actions, draft retention across tabs/programs/polling, save/reload, cancellation, mobile edits, offline controls and 1440/980/390/320px layouts without horizontal overflow. Final screenshots were visually reviewed.
OBS layout and Android validation also passed. All 68 packaged source files match the validated public tree. The 0.9.3 updater accepts this package with unchanged core requirements.

Tests used isolated fake services; no operator broadcast or camera action was performed.
