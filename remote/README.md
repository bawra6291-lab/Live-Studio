# Optional self-hosted remote control

This is a separate, opt-in relay. It is not a deployed public service. Local/LAN use does not need it. The Windows PC makes outbound HTTPS requests; do not expose ports 8865, 8866, 4455 or the camera to the internet.

## Deploy

Requires a Linux Docker host, a domain pointing at that host, and ports 80/443 available for Caddy's TLS certificate provisioning. Hosting, DNS, certificate issuance and production security review are operator deployment gates, not completed by shipping this code.

1. Set `LIVE_DESK_DOMAIN=your-real-domain.example` in your deployment environment.
2. From this directory run `docker compose up -d --build`.
3. Create a workspace: `docker compose exec relay python server.py create-workspace "Temple name"`. Keep the returned workspace ID.
4. Grant an owner, operator or viewer: `docker compose exec relay python server.py grant WORKSPACE_ID owner`. Each grant prints a unique access code once; deliver it privately. Do not put it in screenshots, source control or chat logs.
5. Enroll a PC: `docker compose exec relay python server.py grant WORKSPACE_ID agent --name "Temple PC"`. Paste that agent token into Mobile access → Internet remote access on that PC. Save the HTTPS origin and enable the option. Tokens stay in Windows Credential Manager.
6. Open the HTTPS address on a phone and sign in with the appropriate owner/operator/viewer code. Commands remain disabled when the PC heartbeat is older than 15 seconds.

## Authorization and execution

- Every session, device, command and state read is workspace-scoped. Owner/operator can enable, pause or check. Viewers can only read. Owners can revoke members and PCs. Local credentials, arbitrary shell commands, browser scripts and stream keys are never accepted remotely.
- Cookies are Secure, HttpOnly and SameSite=Strict; browser writes require exact Origin and CSRF. Agent authorization uses an independent high-entropy token over certificate-verified HTTPS. The listener is private to the Docker network; Caddy overwrites the client IP used by login throttling.
- Commands require a live heartbeat, the PC's current boot ID, explicit confirmation and an idempotency nonce. They expire after 45 seconds and are dispatched once. A PC restart, ambiguous delivery or crash never replays them. An unacknowledged dispatched command becomes `unknown`; inspect the PC before a new attempt.
- `accepted` is command acceptance, not proof of successful connection checks or live start. The PC's subsequent status is authoritative. Pausing cancels future starts, ends and camera steps; existing streams continue.
- Revocation cancels queued commands. It cannot recall an operation already accepted or in progress on a PC. Local schedules continue after server/network failure or device revocation.
- Agent records receipt durably before dispatch, limits its ledger to 500 entries and rejects old boot IDs. Server command history remains in SQLite for audit; the UI shows the last 50.

## Operations and limitations

Back up the relay-data volume with SQLite's online backup API or while stopped; restrict backup access because it contains user/workspace metadata and hashed credentials. Keep Docker/Python/Caddy updated. Rotate enrollment/access codes by granting a replacement and revoking the old grant. The host administrator provisions members through the CLI; this pilot has no self-service email, billing, SSO or Google/Meta OAuth authorization broker.

This service is suitable for supervised pilot deployment after testing TLS, network loss, tenant isolation and revocation in your environment. It has automated authorization/queue tests, but no claimed independent penetration test or large-scale load certification. Use PostgreSQL/managed infrastructure and reviewed identity onboarding before a high-volume public product rollout.
