# Live Desk product foundation — development preview

This branch starts converting the ISKCON-specific controller into a configurable product. It is not a production release or a hosted multi-tenant service. Do not merge into the release feed until Windows and real-platform validation are complete.

## Implemented

- One workspace per Windows user, with configurable name, YouTube channel ID, Facebook Page ID, existing YouTube stream key name, OBS configuration and ISAPI camera channel.
- New installations start paused with no programs, no selected destinations and no camera moves. Each new workspace has a stable, unique Windows Credential Manager service name.
- Existing settings migrate in place with a pre-migration backup. Existing schedules, armed preference, OBS profile and legacy Credential Manager service remain intact. The existing ISKCON Page and `YouTube Official Livestream` name remain selected. The legacy channel reference check remains available until an explicit channel ID is saved.
- Up to 24 programs with stable IDs, names, previous livestream references, title templates, daily start/end times and camera steps. New programs start disabled and have no camera actions.
- Setup checklist on Connections, dynamic destination cards and desktop/mobile schedule editing.
- The exact existing OBS stream key must still match a stream owned by the selected YouTube channel, and its name must match the saved stream key name. No new YouTube stream key is created or reset.
- Channel/Page mismatches fail before broadcast creation. Recent unfinished runs block destination changes and program removal. Prepared programs retain their frozen plan.
- Credential editing and OAuth remain local-PC-only; mobile clients require pairing. Existing host/origin/CSRF checks remain.

## Preview setup

Use a separate test Windows user/PC or set `LIVE_DESK_DATA_DIR` to an empty test directory before launching. The normal data directory is retained for migration compatibility; running this branch with that directory migrates its settings. Do not run stable and preview controllers simultaneously.

1. Open Connections on the Windows PC. Enter a workspace name, YouTube channel ID (UC followed by 22 characters), numeric Facebook Page ID and the name of an existing reusable YouTube stream key. Enter the key name, not its secret value. Keep the existing matching key configured in OBS.
2. Save OBS profile, collection, scene and Facebook plugin target. For this developer preview, supply your Google Desktop OAuth client JSON path and Facebook Page token locally. Save settings, then Connect YouTube.
3. Add programs in Schedule. Use an 11-character reference ID from a previous livestream on the selected channel. Its settings, description and thumbnail provide the template. Set the title template with `{date}` and `{program}`; migrated programs can keep the legacy date replacement by leaving it blank.
4. Choose start/end times, opt into camera actions only if wanted, enable the program checkbox and save. Times are IST in this milestone. YouTube and Facebook broadcasts are public.
5. Pass Check connections, inspect the intended OBS scene, then supervise a short scheduled test before unattended use. A connection check does not test starting, ending or camera movement.

## Current completion record

See [WORK-COMPLETION.md](WORK-COMPLETION.md) for the 0.8.0 implementation, external release gates and explicit remaining product limits. Calendar/recovery, credential-free backup, LAN device roles, optional self-hosted HTTPS relay and bundled Windows installer are now implemented.

## Original foundation boundaries (superseded where noted above)

- This milestone is not multi-tenant cloud infrastructure. There are no team roles, internet relay, billing or central account system yet. Phone access remains on the same trusted LAN using the existing paired dashboard.
- Public distribution needs production Google/Meta OAuth onboarding, application verification/review as applicable, signed Windows installation/updates, device enrollment, secure remote transport and tenant authorization. A credential namespace does not provide cloud tenant isolation.
- Version 0.7.0 adds opt-in real browser recording/replay and truthful progress for calibrated workflows. API mode remains the default. Browser actions need operator recording/review and real-site verification; no universal preconfigured site automation is claimed. OBS remains controlled via WebSocket with a visible window. Login/UAC and unsupported native/iframe/plugin workflows are manual or need adapters. See app/VISIBLE-MODE.txt.
- Windows elevation, OBS plugin reload, lock/sleep recovery, expired credentials and platform error recovery still require end-to-end testing. Existing metadata/API errors are not claimed fixed by this product milestone.
- Manual public broadcasts and uncertain partial runs require operator review. This branch does not automatically delete/retry them. Recent unended run records may block destination changes until they fall outside the scheduler's active day range; a reviewed reconciliation workflow is a separate milestone.
- Program execution uses the existing scheduler and its timing windows. This is not an OS service and cannot operate while the PC is off or the desktop agent is closed.
- General time zones, optional single-platform streaming, additional camera vendors and multiple workspaces on one machine are later work.

## Release policy

Development version: 0.8.0. An opt-in pilot ZIP, manifest and PC test guide are available under `updates/pilot/` on this development branch. The stable `main/updates/latest.json` feed is unchanged, so existing users remain on stable 0.5.5 unless they deliberately select the pilot feed. The package uses the exact passing CI source. Validate the real Windows installer handoff, migration, OBS and supervised platform start/end before any public/stable rollout.

## Validation

Automated Python tests cover legacy regression behavior, workspace migration, credential namespace selection, fresh-install defaults, destination binding, immutable internal settings, active-run edit/removal guards, custom plans and selected camera channels. HTTP boundary tests still verify pairing, local-only credential editing, host/origin and CSRF checks. External services are mocked; these tests do not authorize or perform live broadcasts.

Validation now runs through `.github/workflows/validation.yml`: controller regression tests on Windows and Linux, a Windows native dependency/UI smoke check, and isolated desktop/mobile browser flows. See `qa/README.md` and the PR checks for current results and screenshots. The QA server uses temporary settings and fake services; it cannot start automation or authorize accounts. Browser processes are restricted in the local development environment, so browser execution uses GitHub Actions. Real Windows OBS/UAC, live-platform and camera testing on the operator’s PC remain release gates.

The first Windows CI run exposed a path-comparison failure in updater swapping: preparation canonicalized the path while swapping compared the caller’s original spelling. Swapping now checks for symbolic links/junctions before resolving both paths, then requires distinct sibling directories. Regression tests cover equivalent path spellings, unsafe directories and rollback. This finding does not establish the cause of a particular operator’s earlier update failure.
