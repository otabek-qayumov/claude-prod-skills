---
name: railway-diagnose
description: Find out why a Railway-hosted app is slow, "freezes" or loses work — with measurements, not guesses. Use when someone says the app/bot on Railway is slow, hangs, times out, or the AI answers late; or before proposing a migration off Railway.
---

# Diagnose a slow Railway service

"Railway is slow" is almost never one thing. Measure four layers before naming a cause:
resources, request latency per route, deploy churn, and errors. In practice the server is
often idle and the pain comes from slow upstream calls (AI APIs) and frequent deploys.

## 0. Access

- The CLI usually works even when the Railway MCP returns `Unauthorized`. Check `railway whoami`.
- GraphQL (`https://backboard.railway.com/graphql/v2`, bearer = `accessToken` from
  `~/.railway/config.json`) is good for metrics and deployments, but it intermittently answers
  `Not Authorized` under load — retry or fall back to the CLI.
- Read-only by default. Variables, start command and redeploys belong to a live system: ask first,
  and never print variable values into the chat.

## 1. Resources (is the box actually busy?)

```graphql
metrics(projectId, serviceId, environmentId, startDate, sampleRateSeconds: 900,
        measurements: [CPU_USAGE, MEMORY_USAGE_GB, DISK_USAGE_GB, CPU_LIMIT, MEMORY_LIMIT_GB])
```

Report average, max and *when* the max happened. A spike that lines up with a deploy or a
batch job (video transcoding, backups) is a different problem from sustained load.

## 2. Latency per route

`httpLogs` over GraphQL may return a single row. Use the CLI instead:

```sh
railway logs -p <project-id> -s <service> -e production --http --json -n 5000 --since 3d > http.jsonl
python3 scripts/railway_http_stats.py http.jsonl
```

The script prints overall p50/p90/p99 for dynamic requests, the slowest routes by p90, status mix,
upstream errors and every request over 5 s. Static assets are excluded. If p50 is tens of
milliseconds and only AI/upload routes are slow, the server is not the bottleneck.

## 3. Deploy churn

List the last 30–40 deployments with commit messages and timestamps. With a volume attached,
every deploy is stop → start (no overlap): requests fail for several seconds, in-flight background
work dies, and frameworks with skew protection force open pages to reload. Seven deploys during
working hours feel like "it keeps freezing" even when each one is healthy.

Check the deploy logs for `npm error signal SIGTERM`: a start script like
`npm start` → `sh -c "migrate && next start"` does not forward SIGTERM, so the app is killed
instead of draining. Fix with `exec` in a start script and a drain period
(`RAILWAY_DEPLOYMENT_DRAINING_SECONDS`).

## 4. Errors

Structured JSON logs are parsed into attributes and their values keep JSON quotes, so filters on
the message miss them. `@level:error` works; attribute filters need the quoted value.
Look for: upstream API timeouts, `fetch failed` to third-party APIs (no retry?), and client aborts
(499 — usually harmless).

## Report

One table per layer, then the causes ranked by user impact, each with the number that proves it.
Say explicitly what is *not* the problem (e.g. "CPU averages 0.01 vCPU; this is not capacity").
