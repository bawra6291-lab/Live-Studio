# Live Desk 0.10.4 pilot

Improves daily darshan photo suggestions for modest framing/zoom and dress changes. Uses grayscale shape and upper-frame structure instead of clothing colour. No new API key or dependency.

- Slot labels follow Post_Structure 2.0, including straight/right/left full and half body.
- Show only photos to check focuses on uncertain matches, missing photos and format warnings.
- Use this photo acknowledges a suggestion for the current review; it does not publish, train a model or save learned examples.
- Existing private reference files remain compatible. Originals are unchanged.

On the PC, when live and recording are idle and automation paused, open Updates, Check for updates, then Download & install. The existing pilot feed remains updates/pilot/latest.json. Saved connections, reference and schedules remain in place.

After updating, open Social Media > Darshan batch > Upload & arrange photos. Review flagged matches, then view the full order and create five unapproved drafts. Platform approval remains separate.

Both supplied 17-photo sets matched the visually reviewed order in local engine comparisons, with 4 and 10 review flags. This is limited sample evidence, not guaranteed semantic recognition or unseen-day accuracy. Operator photos are not bundled or uploaded to this repository.

YouTube photos and Instagram portrait still require manual upload. Existing file format/size requirements remain. See build-report.json for the exact tested source and validation runs.
