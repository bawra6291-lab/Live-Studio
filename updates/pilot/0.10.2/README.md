# Live Desk 0.10.2 — Bulk library photo deletion

## Update the existing app

Finish active live/recording/replay and pause both live automation and Social Media posting. In Updates, Check for updates → Download & install. The existing pilot feed serves 0.10.2; saved connections, credentials, schedules and Official stream-key selection stay in place.

`https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json`

## Delete photos together

1. Social Media → Media library.
2. Select all photos, or tick Select for deletion on specific files.
3. If unused drafts or the saved darshan batch reference these photos, optionally tick **Also remove unused drafts and clear batch slots for these photos**.
4. Delete selected. Review the exact filenames, unused draft titles, cleared slot numbers and retained-file reasons.
5. Confirm. The result reports deleted/retained media and removed drafts. Cancel keeps all files intact.

Approved/queued, posting, posted, review, manual-ready and manually-completed items protect their media. Cancel an unused queued/manual-ready item in Posting queue before reviewing cleanup again. Started or uncertain posts need inspection; cleanup does not delete or send any social platform post. The optional checkbox removes entire unused draft posts listed in the review; it clears only selected eligible photo assignments in the saved batch. Caption and posting times remain. Original PC files are not removed.

Up to 500 files per operation. Select all photos selects images, while individual deletion selections can include videos. Busy local files are retained. The server checks current references before confirmation, and a changed draft/batch/selection requires a new review. Files are staged locally before committing metadata, with recovery after interrupted removal. Browser tests use fixture media only and do not access user account photos.

[Build report](build-report.json) · [0.10.1 darshan structure](../0.10.1/README.md). This update does not add automatic YouTube Community or Instagram 3:4 photo posting.
