# Live Desk Internet Control — prepared deployment

Status: configuration staged; no public domain or running relay yet. The public-domain action was rejected by automatic approval review because internet exposure requires explicit deployment approval. Do not retry exposure or use a workaround before that approval.

Project: Live Desk Internet Control, 72181a6f-6279-4c58-a343-1fa16a365104.
Environment: production, 4dcf77c9-d093-48c6-bb28-d613ccb9b006.
Service: live-desk-relay, 992a7d18-cd14-4ddb-b080-026857c960cf.
Volume: live-desk-pairing-data, 63767951-e274-43ad-adba-09aea834a03e, 500 MB mounted /data.

Single Python/Docker relay, /remote root, Dockerfile, health /health, always awake, failure restart. Source is pinned to a tested commit. Separate random owner and agent grants are provisioned by hashed bootstrap values in a private variable; plaintext tokens are in the owner's private setup backup. No PC stream keys, OAuth secrets, Page tokens, camera credentials or arbitrary remote shell/browser commands are accepted.

After owner authorizes deployment and public HTTPS exposure:
1. Re-read the staged changes and deploy the pinned source. Without an origin the service offers health only; API controls return 503.
2. Generate the Railway public domain on port 8080; set PUBLIC_ORIGIN to that exact HTTPS origin and redeploy. Verify the HTTPS certificate and /health configured=true before distributing the address.
3. Verify login, CSRF, distinct PC agent authorization, saved sessions/restart, fresh heartbeat and disconnected controls using an isolated agent/workspace; do not arm the actual temple PC. Check mounted database survives restart; remove/bootstrap-disable the seed after initial provisioning if operationally appropriate.
4. Privately supply that HTTPS address and the separate PC enrollment / phone access code from the private backup. PC local Internet remote access saves agent grant once. Phone app pairs once. Never send stream/platform secrets through the relay.
5. Operator then performs actual phone mobile-data reconnect and supervised Enable/Pause testing with their PC. Stream/camera acceptance remains with the operator.

Running compute, volume and traffic follow Railway usage billing/account credits. Exact monthly cost depends on plan/traffic; no new payment plan was purchased. Keep one replica for SQLite, arrange private database backups, monitor storage and login throttling, and independently review production security/load before a multi-customer public launch. This relay is an opt-in supervised pilot, not SSO/billing or a platform OAuth broker.
