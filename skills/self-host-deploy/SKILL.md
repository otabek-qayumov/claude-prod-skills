---
name: self-host-deploy
description: Ship a web app or bot to your own VPS the professional way — image built in CI and pulled by the server (no source on the box), HTTPS for every tenant subdomain without DNS API keys, deploys with health-checked automatic rollback, graceful shutdown that does not kill background work, and a fixed deploy window. Use when moving off a PaaS, setting up a new server, or when deploys cause downtime or lost jobs.
---

# Self-hosted deploys that do not hurt users

## Principles

- **The server never sees the source.** CI builds the image and pushes to a registry (GHCR); the
  server only `docker pull`s an immutable tag (the commit SHA). Compose files have `image:`, never
  `build:`. Rollback = previous tag.
- **Runtime image contains only what runs.** Multi-stage build; copy build output, not `src/`, tests
  or docs. Run as a non-root user. `.dockerignore` excludes databases, uploads, `.env`.
- **Deploy is boring and scheduled.** Merges are tested on every push; production gets them once a
  night (or by a manual button), not seven times during working hours.

## Graceful shutdown (where background work usually dies)

1. Signals must reach the app. `npm start` → `sh -c "migrate && next start"` swallows SIGTERM. Use a
   start script that ends in `exec <server>`; run with `init: true` (tini) so zombies are reaped.
2. Give it time: `stop_grace_period: 120s` (longest AI call + margin). Next.js `next start` waits for
   pending `after()` callbacks on SIGTERM — only if it gets the signal and the time.
3. On PaaS: set the drain period (e.g. `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`).
4. Still journal in-flight jobs (see `durable-background-jobs`): crashes do not send SIGTERM.

## HTTPS for `*.example.com` tenants without a DNS API token

Caddy on-demand TLS issues a certificate on the first request — but only for hosts your app approves:

```caddyfile
{
	email {$ACME_EMAIL}
	on_demand_tls {
		ask http://app:3000/api/tls-allowed
	}
}
https:// {
	tls { on_demand }
	reverse_proxy app:3000
}
http:// {
	redir https://{host}{uri} 308
}
```

`/api/tls-allowed?domain=x` returns 200 only for the apex, `www` and existing tenant slugs; 404 for
everything else (scanners hit random subdomains — do not burn Let's Encrypt rate limits on them).

## Deploy with automatic rollback

`templates/deploy.sh` runs on the server, invoked by CI over SSH with a **forced command**
(`command="/srv/app/deploy.sh",no-pty,no-port-forwarding ssh-ed25519 ...`) so the CI key can do exactly
two things: `status` and `deploy <sha>`. It validates the tag, takes a lock, pulls, switches the tag in
`.env`, waits for the container health check, and on failure prints the last logs and switches back.

CI workflow outline (`templates/deploy.yml`): gate on a repo variable (`DEPLOY_ENABLED=1`) so it is
inert until the server exists; on schedule skip when the server already runs `HEAD`; run lint/types/
tests; build+push `:<sha>`; `ssh deploy <sha>`.

## Cutover from a PaaS (one evening)

1. Days before: copy the big immutable data (videos) to the new server.
2. Lower DNS TTL to 60 s a day ahead.
3. At night: freeze the old app (`SIGSTOP` the server process over SSH — match it with a pattern like
   `[n]ext-server` so the SSH shell does not freeze itself), copy databases + new files, verify
   integrity, stop the old deployment (keep the service and volume for rollback).
4. Start the new stack, switch DNS, test every tenant, the bot (send a message) and backups.
5. Keep the old platform stopped-but-intact for a week.

## Verify, then say "live"

Live means: the running container's image ID equals the tag you deployed, `/health` is 200 from the
outside, and one real user flow works. A green CI run proves an image exists — nothing more.
