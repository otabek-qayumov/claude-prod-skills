---
name: durable-background-jobs
description: Make background work survive deploys and crashes — Celery + Redis configured for at-least-once delivery, a journal for in-process jobs (after()/fire-and-forget), idempotent retries, and safe retry rules for external APIs like Telegram. Use when users report "the bot didn't answer", jobs vanish on deploy, or when adding workers/queues.
---

# Background jobs that do not vanish

Fire-and-forget work (`after()`, `setTimeout`, `asyncio.create_task`) lives in process memory. Every
deploy or crash deletes it silently: the user saw "⏳ Processing…" and never got an answer.

## Option A — keep jobs in-process, but journal them

When moving to a queue is not possible yet:

1. Before starting the job, insert a row: `{type, payload (ids only, no secrets), process_id, attempt}`.
   Start the insert *synchronously* in the request — if it is queued behind the job itself, a crash in
   between leaves no trace.
2. Delete the row in `finally`.
3. On boot, rows whose `process_id` is not the current one are orphans. Claim each with a conditional
   delete (`DELETE ... WHERE id=? AND process_id=?` → affected = 1) so two instances never both take it.
4. Decide per type:
   - **re-run** when the job is idempotent because its state lives in the database (a conversation step
     guarded by a lease, a scoring job that checks "already scored");
   - **tell the user** ("the server restarted, please send it again" — edit the "⏳" message) when re-running
     could duplicate side effects (creating a task, sending an invoice);
   - **drop** when older than a few hours (nobody is waiting any more).

## Option B — a real queue: Celery + Redis

```python
app.conf.update(
    task_acks_late=True,               # ack after success, not on receipt
    task_reject_on_worker_lost=True,   # worker killed -> task goes back to the queue
    worker_prefetch_multiplier=1,      # a slow AI job does not hoard short ones
    broker_transport_options={"visibility_timeout": 2 * 3600},  # > your longest task
    task_soft_time_limit=15 * 60, task_time_limit=20 * 60,
    task_queues=(Queue("default"), Queue("ai"), Queue("video")),
    task_routes={"app.ai.*": {"queue": "ai"}, "app.video.*": {"queue": "video"}},
    timezone="UTC", enable_utc=True,         # or your users' timezone for beat schedules
    accept_content=["json"], task_serializer="json",
)
```

- At-least-once means **every task must be idempotent**: check state before acting, use unique keys.
- Separate queues by latency class; run `video` with concurrency 1.
- One `beat` instance only. Fan out per tenant (`backup_all` enqueues `backup_one(schema)`) so one
  failure does not stop the rest and each retries on its own (`autoretry_for`, `retry_backoff`).
- Async code inside a prefork worker: create the DB engine per task with `NullPool` — asyncpg
  connections are bound to the event loop that created them.

## Retries against external APIs (Telegram as the example)

A blind retry can deliver a message twice. Classify:

- **Safe to retry on any network error**: reads and idempotent writes — `answerCallbackQuery`,
  `editMessage*`, `deleteMessage`, `get*`, `setWebhook`, `sendChatAction`.
- **`sendMessage` & co.**: retry only when the request certainly never arrived — connection refused,
  DNS failure, connect timeout (`ECONNREFUSED`, `ENOTFOUND`, `EAI_AGAIN`, `UND_ERR_CONNECT_TIMEOUT`).
  Not after a reset or a read timeout.
- **HTTP 429**: wait `retry_after` if short (≤ 5 s), otherwise give up and log. **5xx**: retry with backoff.
  **4xx**: never retry.
- Two retries (≈0.6 s, 2 s) cover the transient blips seen in practice; log the final failure.

Unanswered callback queries leave the button spinning — the most visible "frozen bot" symptom.

## Schedules

Do not register 15 hourly jobs at the same instant (`setInterval(fn, 1h)` × 15 at boot = all fire
together, every hour). Give each its own minute offset.
