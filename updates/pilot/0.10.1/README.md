# Live Desk 0.10.1 — Darshan posting structure

This pilot follows the supplied Post_Structure PowerPoint. It creates five separate, unapproved drafts from 17 operator-imported photos. It never uses the PPT previews as posting originals.

## Update the existing app

Finish active live/recording/replay. Pause live automation and Social Media posting. In App updates, use the existing pilot address, Check for updates, then Download & install. Connections, Windows credentials, live schedules, media and the Official YouTube stream-key selection stay in place.

`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

## Prepare the batch

1. Social Media → Darshan batch → Import today's photos (JPG/PNG; export RAW first).
2. Match the example DSC filenames, or assign today's photos by subject. Each slot is numbered. Edit crop saves a new copy and preserves the slot; originals remain intact.
3. Post 1: seven portrait photos, 3:4, first photo is cover. Post 2: ten landscape photos, 4:3, first photo is cover. Landscape JPG copies must meet the API requirements shown in the app.
4. Facebook: landscape 1–4 → portrait 1–7 → landscape 5–10, 17 photos in one post, full altar first.
5. Enter shared caption and three IST times. Save batch → Create five drafts. Review each draft's exact caption/order/account/time before approval.

## Which posts are automatic?

| Destination | Structure | Method |
| --- | --- | --- |
| Instagram portrait | 7 photos, 3:4 | Manual photo package, crop retained |
| Instagram landscape | 10 photos, 4:3 | Approved API queue |
| YouTube Community portrait | 7 photos, 3:4 | Manual photo package |
| YouTube Community landscape | 10 photos, 4:3 | Manual photo package |
| Facebook | 17 mixed photos | Approved API queue; supervised account test required |

For manual items, Preview & approve freezes the package as Ready · manual upload. Download ordered photos provides numbered files (01 is cover), caption.txt and order.json. Open the platform, check the intended account, upload in number order, paste the caption and set the platform's posting time. The saved Live Desk time does not itself schedule these manual items. Mark completed is the operator's confirmation, not an API-verified receipt. The official YouTube Data API reference exposes no Community create-post method; this build adds no browser-click workflow for photo posting.

API items run only after approval AND Enable posting, while the PC is awake. Existing live-output and preparation guards still apply. Errors pause posting for review and no uncertain request is retried automatically. Actual platform permissions, Facebook 17-photo acceptance and Instagram media hosting must be tested on the operator account.

Repeated Create five drafts for the same saved batch returns the same drafts. Editing the batch preserves previously created drafts: cancel obsolete drafts before approving replacements. [Build report](build-report.json) lists the tested source, checks and limits. [Photo posting help](https://support.google.com/youtube/answer/7124474) · [YouTube Data API reference](https://developers.google.com/youtube/v3/docs).
