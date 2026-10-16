# Live Desk 0.14.1 — YouTube Chrome channel verification

Fixes the channel-setting parser used at “Checking Chrome channel”: read the labelled input value, sibling/associated fields and open shadow-root fields, including channel IDs ending in a hyphen. Unrelated channel links and hidden values are not accepted as identity evidence. Reopening the identity tab waits for the new document, and the account is checked again before Publish.

Sign-in/consent redirects, navigation errors and unavailable Advanced settings now have distinct actionable errors. No channel auto-switching, credentials extraction, login replacement or repeat publish click is added. Existing Chrome profile and media order are retained.

Update in Live Desk → Updates → Check for updates → Download & install, with automation paused and no live/recording active. After restart verify version 0.14.1. Review YouTube for any prior post, then prepare a fresh YouTube draft and use Send to YouTube. Do not replay an uncertain earlier dispatch.

Validation: 317 controller tests on Windows/Linux; 24 remote controller tests; 21 dashboard flows; 20 actual local Chromium/CDP YouTube adapter cases; Windows native lifecycle and installer/runtime/uninstall; Android and OBS helper checks passed. Update staging from 0.14.0 passed and all 102 package files match the tested source. No runtime dependency change.

The dashboard fixture now polls the exact Telegram job to completion: Playwright waitForFunction previously treated its returned Promise as truthy and inspected a partial album receipt too early. This change is test-only.

Testing used isolated pages and photos. No real accounts were posted to. The user's actual Chrome page was not available, so live-account acceptance remains pending. The original supplied studio document remains unchanged.
