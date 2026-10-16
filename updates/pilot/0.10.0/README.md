# Live Desk 0.10.0 — Social Media pilot

The existing Windows app now includes a Social Media workspace for Facebook Pages, linked Instagram professional accounts and YouTube video uploads. It ships with posting paused. Saving a draft does not publish it; an exact revision must be approved, then posting enabled.

## Existing installation
Finish active live/recording/replay, pause live automation and Social Media posting, then open **Updates → Check for updates → Download & install**. Confirm **0.10.0** after restart. Core runtime requirements are unchanged; no new renderer or account reset is needed.

Use the existing opt-in pilot feed:
`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

## First setup
1. Open **Social Media → Accounts → Check posting accounts** on the PC.
2. Facebook and YouTube reuse Connections and Windows Credential Manager. The existing Official stream-key selection is retained.
3. If Instagram is linked to the selected Page, choose **Use detected Instagram account → Save Instagram account**. Grant the Page/Instagram publishing permissions in your own Meta app if needed.
4. Import media, prepare a draft, check its preview, and choose a future IST time. Keep posting paused until you intentionally approve a supervised first post.
5. **Save draft → Preview & approve → Enable posting** is the publishing flow. It creates real platform posts.

## Included
- Immutable JPG/PNG/MP4/MOV library, up to 25 imports per batch, 1 GB/file and 5 GB/library.
- Photo crop/position, brightness/contrast/colour, optional text watermark; edited copies are JPG up to 1600px on the longest side.
- Caption templates in Hindi/English, platform selection, YouTube visibility/audience and IST scheduling.
- Facebook text/photo collections/video; Instagram JPG/carousel/Reels adapters; YouTube resumable-protocol video uploads.
- Persisted approved revisions and frozen account IDs; stale device edits are rejected.
- Progress receipts, late-window holds, pause after uncertain writes, restart recovery, read-only verification of an existing post ID and sharing published links.
- Paired Wi-Fi operators can prepare/approve. Viewer sessions cannot read unpublished captions or original media.
- Posts wait during observed live OBS outputs and the preparation/start window, protecting live automation.

## Limits and account verification
Posting uses APIs; the visible browser-click recipes currently cover live-stream workflows. Actual Page/Instagram permissions, YouTube app audit restrictions and Instagram fetching of hosted JPGs need a supervised account test. No real account, OBS or camera was used by automated validation.

Export RAW to JPG before import. Instagram video Reels need the same video at a public HTTPS URL; hosting that video is a separate setup. JPGs use unpublished Page photos as fetchable media, with receipts retained.

YouTube Community posts are unsupported. WhatsApp currently uses Share/copy link; no Group/Community/Channel message is automatically sent. The existing internet relay is not a social media uploader/composer in this pilot. See [the full operator guide](../../../app/SOCIAL-MEDIA.txt).

## Evidence
Source: `55fae08e408e18926823162de3de845114b1b2b6`.
[Development validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38398104017) passed 234 app tests on Windows/Linux, social browser flows at 1440/980/390/320px, native desktop lifecycle and taskbar identity, and Windows installer build/install/uninstall.
[Android validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38398104074) and [OBS layout validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38398104102) passed.
The 0.9.4 updater accepts this package. All 74 payload files match the tested public source; no operator media or credentials are packaged.
