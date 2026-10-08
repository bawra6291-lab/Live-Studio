# Live Desk Internet Control — deployed pilot

Status: deployed after explicit operator approval on 8 October 2026. Public HTTPS origin: https://live-desk-relay-production.up.railway.app. PC enrollment and the operator's actual cellular-network acceptance remain pending.

Project: Live Desk Internet Control, 72181a6f-6279-4c58-a343-1fa16a365104.
Environment: production, 4dcf77c9-d093-48c6-bb28-d613ccb9b006.
Service: live-desk-relay, 992a7d18-cd14-4ddb-b080-026857c960cf.
Volume: live-desk-pairing-data, 63767951-e274-43ad-adba-09aea834a03e, 500 MB mounted /data.
Current successful deployment: 37cd66d6-15ff-48da-869f-a000e0d475f7.
Pinned relay source: 9edce04918891b9aa7f69c19cda56e5bc19fad65, /remote Dockerfile.

One Python replica behind Railway-managed TLS, health /health, PUBLIC_ORIGIN set to the exact HTTPS origin, listener port 8080. Pairing is stored in SQLite on the persistent volume. Separate random owner and PC agent grants were provisioned using hashes in private bootstrap configuration. Plaintext codes and the Android permanent signing key stay in private backups outside this repository. No PC stream keys, OAuth secrets, Page tokens, camera credentials or arbitrary remote shell/browser commands are accepted.

## Hosted checks passed

- Standard Python HTTPS verification enabled; no insecure TLS override or redirect accepted. /health returned 200 with configured=true.
- Unauthenticated state rejected; invalid code and a PC agent token rejected by phone login.
- Owner login accepted with Secure, HttpOnly, SameSite=Strict, 365-day renewal cookie.
- Browser writes without CSRF or with a foreign Origin rejected.
- Owner access code rejected as agent authorization. Correct agent grant authenticated, but intentionally invalid heartbeat rejected before any device update.
- Actual temple PC remained offline and command history empty; no Check/Enable/Pause/end, live or camera command was enqueued.
- An authenticated session created on deployment 348d6407-94bc-4c51-899a-812165c80540 stayed valid after successful container redeployment 37cd66d6-15ff-48da-869f-a000e0d475f7. This verifies the mounted pairing database survived container replacement. The temporary QA session was logged out afterwards.
- Service settled online with one running replica, its volume attached and no pending deployment work.

## Operator one-time setup

1. Local PC dashboard > Mobile access > Internet remote access: save the HTTPS origin and the private PC enrollment token, tick Enable internet remote control, then Save remote access and confirm. Windows Credential Manager retains the token.
2. Android companion 0.2.0: save the same HTTPS origin and pair with the separate phone/workspace access code from the private operator setup file. Internet pairing survives normal restarts and same-signer updates. Logout, revocation, app data deletion, database loss or 365 days of inactivity require pairing again.
3. Turn off phone Wi-Fi, use cellular data and verify PC online/Check connections. Review the real saved schedule before confirming Enable automation. PC and Live Desk must remain running. Pause stops future automation; it does not end an existing live.
4. Detailed schedule/camera editing remains in the PC/local LAN dashboard. Real streaming/camera and actual phone-cellular tests require supervised operator acceptance. No router port forwarding is needed.

Compute, volume and traffic follow Railway usage billing/account credits. No new payment plan was purchased. Keep one SQLite replica, arrange private database backups and independently review security/load/disaster recovery before a multi-customer public launch. This is an opt-in supervised pilot, not SSO/billing or a platform OAuth broker.
