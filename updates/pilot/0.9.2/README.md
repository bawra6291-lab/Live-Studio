# Live Desk 0.9.2 — desktop window

The dashboard can now open in a native Windows WebView2 window, while the existing controller continues independently. Closing or minimizing this window does not stop schedules, phone control or OBS. Reopening uses the same controller and brings the viewer back. Browser fallback remains available.

## Existing installations

1. Finish active lives/recordings/replay outputs and pause automation.
2. In Updates, check and install 0.9.2 from the existing pilot feed.
3. Open **PC controls → Desktop app window → Set up desktop window** once. Confirm and wait for the component download.
4. If WebView2 Runtime is missing, use the official Microsoft link in that panel, then **Open desktop window**.
5. Test close/reopen while idle before a supervised live test. Saved connections, schedules and the Official stream key are reused.

**Use browser dashboard** changes the saved dashboard preference back to the browser. **Open desktop window** selects desktop again. Only **Quit Live Desk on this PC** or tray Quit stops the background app.

## Implementation and evidence

Renderer packages are isolated from the host dependencies. The viewer is a separate no-console process, receives the current local pairing URL through an inherited pipe, and exposes no custom Python bridge. Existing HTTP authentication and CSRF checks remain in use. YouTube/Facebook login and visible workflows retain their browser flow.

Source commit: `a561b91b4ac518e9e923ab0b26da7b686495d200`.
Windows/Linux controller, browser dashboard, Windows installer and native window lifecycle checks passed in [Development validation](https://github.com/bawra6291-lab/Live-Studio/actions/runs/38332798515). The first Windows run found a blocking pipe reader on window close; this was fixed before publication and the close/reopen test now passes.

No live-platform or user-PC test was performed. This is a pilot release; inspect the actual PC during the first live test.
