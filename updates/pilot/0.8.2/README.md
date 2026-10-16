# Live Desk 0.8.2 — use your existing Chrome login

This pilot adds an explicit connection to the normal running Chrome. The previous 0.8.1 release only reused Live Desk's separate browser profile; it did not meet the requirement to use the operator's normal Chrome.

## Update the existing app

Finish any active live, recording and replay buffer normally. Finish workflow recording and pause automation. In Live Desk → Updates → Open update controls, use the existing pilot feed:

```
https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/pilot/latest.json
```

Check for updates, confirm **0.8.2**, then Download & install. Wait for app restart. Existing settings, credentials, schedules and the Official stream selection remain in place.

## First browser check — no schedule or live action

1. Keep your normal logged-in Chrome window open. In that Chrome open `chrome://inspect/#remote-debugging` and enable **Allow remote debugging for this browser instance**. This needs Chrome 144+ and grants access to signed-in browser pages.
2. Open **Visible automation** in Live Desk on the Windows PC. Leave execution mode **API automation** for this initial check. Choose browser **My running Chrome (existing login)**, then **Save mode & browser**.
3. Click **Connect my Chrome**. Chrome may ask permission; allow only the connection you requested from Live Desk. The app retains that socket for subsequent operations, instead of reconnecting for each click.
4. Select Facebook preparation, then **Open site / sign in**. This navigates a managed tab in your existing Chrome. It must not launch a separate Chrome window/profile. Confirm the correct official Page destination before taking any publishing action. Browser sign-in alone is not proof of the right Page.
5. Do not create another live to check the connection. Recording/replay still requires reviewed workflows and supervised calibration. Keep the existing **YouTube Official Livestream** key; do not reset it or select Default.

The adapter reads only Chrome's debug marker in the standard Windows stable Chrome User Data directory and connects to a loopback WebSocket. It does not read/copy cookies or profile website files. The standard inspect server can be WebSocket-only; this mode does not rely on `/json/version`, `/json/list` or `/json/new`.

One managed tab is reused per service during an app session; existing personal tabs are left alone. Disconnect control leaves browser windows/tabs open. Restarting Chrome or Live Desk requires **Connect my Chrome** again locally and Chrome's permission. Missing, denied or lost connection fails without launching a replacement browser or blindly repeating a dispatched action.

Separate Live Desk browser remains an explicit alternative with its own persistent website login. Custom Chrome channels/profile roots, automatic security/login/UAC handling, universal website recipes and native OBS mouse clicks are not added. API verification credentials remain separate from website login.

CI checks the browser transport and retained dummy login against a localhost Chromium fixture. The actual Windows inspect permission prompt, signed-in YouTube/Facebook account selection and real camera actions require the operator's supervised acceptance check.
