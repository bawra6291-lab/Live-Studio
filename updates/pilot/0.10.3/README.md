# Live Desk 0.10.3 — Upload and arrange daily photos

## Install
Use the existing opt-in pilot feed in Updates. Finish live/recording/replay, pause live automation and Social Media posting, then Check for updates > Download & install.
Saved connections, schedules, imported media and the selected Official stream key are retained.

## One-time reference
Social Media > Darshan batch > Import reference file (once).
Import the private Live Desk reference JSON supplied to the operator. It contains 17 small ordered JPG previews: 7 portrait then 10 landscape.
The reference is stored privately on that PC. It is available only to authenticated operators, never added to posting assets, never shipped in this repository or release, and is not included in normal polling responses.

## Daily workflow
1. Upload & arrange photos: choose today's edited photos together, up to 25.
2. The browser compares only this upload with the saved reference and suggests the 17 slots. Names need not match.
3. Review covers and order. Choose a replacement only where needed; selecting a photo already assigned swaps the two positions.
4. Set the caption and three times, then Review order & create five drafts.
5. Approve the destination drafts in Posting queue. Only approved API posts run when posting is enabled.

Original uploaded bytes are preserved. No automatic crop, colour change or resize is applied to posting photos. Extra or unmatched photos stay in the library. Old library photos do not fill missing slots.

## Limits
This is visual similarity to a fixed reference, not semantic deity recognition. Different daily clothing, backgrounds or camera angles can be mismatched. Every proposed order needs operator review. Tests with renamed, shuffled, exposure-adjusted/recompressed reference photos do not prove accuracy on future daily photos.
Facebook and Instagram landscape retain the existing API posting queue. YouTube Community photos and Instagram 3:4 portrait still use manual ordered packages. This release does not implement automatic browser photo publishing.
No actual platform posts, live streams or camera movements were performed in validation.
