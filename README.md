# claude-prod-skills

**Battle-tested [Claude Code](https://claude.com/claude-code) skills for running, migrating and shipping production systems.**

Every skill here was distilled from real work on a live multi-tenant product — a Railway outage
investigation, a SQLite → PostgreSQL migration of 7 databases, a Next.js → FastAPI rewrite with a
"no text may change" rule — and every script was run against real data before it was written down.
The pitfalls listed are the ones that actually happened.

## Install

```sh
/plugin marketplace add otabek-qayumov/claude-prod-skills
/plugin install prod-skills@claude-prod-skills
```

Or copy any folder from `skills/` into `~/.claude/skills/`.

## Skills

| Skill | Use it when | Ships with |
|---|---|---|
| [`railway-diagnose`](skills/railway-diagnose/SKILL.md) | "The app on Railway is slow / freezes / the AI answers late" | per-route latency analyser for `railway logs --http --json` |
| [`prisma-to-postgres`](skills/prisma-to-postgres/SKILL.md) | Moving Prisma + SQLite (incl. one DB per tenant) to PostgreSQL | Prisma → SQLAlchemy generator (FK cycles, comments, Prisma defaults); verified copier (counts, checksums, orphans, sequences, all-or-nothing) |
| [`golden-parity-port`](skills/golden-parity-port/SKILL.md) | Rewriting a live product in another language without changing behaviour | golden-fixture pattern + a table of JS/Python semantics that silently differ |
| [`verified-backups`](skills/verified-backups/SKILL.md) | Adding/auditing backups, before any migration | per-schema `pg_dump` with restore drill and row-count comparison |
| [`self-host-deploy`](skills/self-host-deploy/SKILL.md) | Leaving a PaaS; deploys cause downtime or lost jobs | forced-command deploy script with health-checked rollback; nightly deploy workflow; Caddy on-demand TLS for tenant subdomains |
| [`durable-background-jobs`](skills/durable-background-jobs/SKILL.md) | "The bot didn't answer"; jobs vanish on deploy | Celery + Redis settings for at-least-once; job journal pattern; safe Telegram retry rules |
| [`repo-state`](skills/repo-state/SKILL.md) | Start of any session that edits or deploys | three checks before touching code |
| [`brand-identity`](skills/brand-identity/SKILL.md) | Logo and identity work | process and quality bar |
| [`web-3d-art-direction`](skills/web-3d-art-direction/SKILL.md) | Premium real-time 3D on the web | art-direction workflow |

## Principles behind them

- **Measure before naming a cause.** Numbers in the report, not adjectives.
- **Done means proven.** A migration is done when every table's checksum matches; a backup exists when
  it has been restored; a deploy is live when the running image SHA matches.
- **Fail loudly, write nothing.** Scripts run in transactions and exit non-zero on the first doubt.
- **No secrets, ever.** Nothing in this repo contains credentials, hosts or customer data.

## O'zbekcha

Bu Claude Code uchun skill'lar to'plami: production tizimlarni tekshirish, PostgreSQL'ga ko'chirish,
kodni boshqa tilga mantiq va matnni buzmasdan o'tkazish, tiklash bilan tekshirilgan zaxira, o'z serverga
deploy va yo'qolmaydigan fon ishlari. Har biri haqiqiy loyihada sinalgan. O'rnatish — yuqoridagi ikki buyruq.

## License

MIT
