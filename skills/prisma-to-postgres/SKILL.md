---
name: prisma-to-postgres
description: Move a Prisma + SQLite app (one file or one file per tenant) to PostgreSQL with SQLAlchemy/Alembic, and prove that every row arrived. Use when migrating off SQLite, splitting tenants into PostgreSQL schemas, generating SQLAlchemy models from schema.prisma, or verifying a data migration.
---

# Prisma + SQLite → PostgreSQL, verified

A migration is finished when you can show, per table, that the target holds exactly what the source
held — not when the copy command exits 0. Everything below serves that one claim.

## 1. Models from the schema, not by hand

```sh
python scripts/prisma_to_sqlalchemy.py prisma/schema.prisma app/models/tables.py --id-func app.ids:new_id
```

- snake_case names (`createdAt` → `created_at`), reserved words renamed (`User` → `users`);
- Prisma's implicit referential actions reproduced (required → RESTRICT, optional → SET NULL,
  onUpdate CASCADE) — the generator raises on anything it does not understand instead of guessing;
- `///` docs become PostgreSQL comments;
- keep ids as they are (cuid strings): links, bot `callback_data` and logs contain them. New ids should
  keep the same shape.

**Check the generated schema against the real database, not only against the Prisma file.** Applied
migrations can differ from `schema.prisma`. Compare `PRAGMA table_info` / `PRAGMA foreign_key_list`
of a production copy with the model metadata: column set, NOT NULL, type, FK target and ON DELETE.

Do not run `prisma format` in the source repo while doing this — it reformats the whole file and
buries your one-line change in a 600-line diff.

## 2. Tenants → schemas

One SQLite file per tenant maps naturally to one PostgreSQL schema per tenant (`t_<slug>`), plus a
catalog schema. Isolation stays physical, and a single tenant can be dumped, restored or dropped alone.

- Models carry no schema; bind per request:
  `engine.execution_options(schema_translate_map={None: schema})`.
- Validate the slug before turning it into an identifier (`^[a-z][a-z0-9-]{1,30}$`, `-` → `_`).

Alembic, multi-schema (`alembic/env.py`): loop over schemas; for each one `CREATE SCHEMA IF NOT EXISTS`,
`SET search_path`, then `context.configure(connection=conn.execution_options(schema_translate_map={None: s}),
version_table_schema=s, include_name=...)`. Pass `-x schema=<name>` to run a single schema.

## 3. Three Alembic traps (each one bit a real migration)

1. **Autogenerate deletes its own version table.** In a multi-schema setup autogenerate sees
   `alembic_version` as an extra table and emits `op.drop_table('alembic_version')`; the upgrade then
   fails on its final INSERT. Filter it:
   `include_name=lambda name, type_, parent: not (type_ == "table" and name == "alembic_version")`.
2. **FK cycles.** Tables that reference each other (department ↔ position ↔ users) cannot be created in
   any order. The generator marks those keys `use_alter=True` — and `op.create_table` then **silently
   skips them**. Count FKs after upgrade; add the missing ones with `op.create_foreign_key(...)` at the end
   of `upgrade()` (and `op.drop_constraint` at the start of `downgrade()`).
3. **Identifier length.** PostgreSQL truncates names at 63 characters; generated index names are
   shortened with a hash so two long names cannot collide.

Prove the migration in CI on an empty schema: `upgrade head`, `check` (no drift), `downgrade base`.

## 4. Copy and verify

```sh
alembic -x schema=t_acme upgrade head          # create tables first
python scripts/sqlite_to_postgres.py --dsn postgresql://... --db acme.db:t_acme --db other.db:t_other
```

Per schema, in one transaction: COPY with FK triggers off → read every table back and compare count +
checksum → orphan check on every FK → identity sequences moved past `max(id)`. Any failure rolls the
schema back; nothing half-written survives.

Conversions that matter:
- Prisma stores `DateTime` in SQLite as **epoch milliseconds (INTEGER)**; rows written by raw SQL
  defaults are text (`CURRENT_TIMESTAMP`). Handle both; store `timestamptz` UTC; compare at ms precision.
- SQLite booleans are 0/1; SQLite columns accept any type (an INTEGER column can hold text) — fail
  loudly with the row number instead of coercing silently.
- Check 32-bit range for `integer` columns (file sizes, counters) before choosing `integer` over `bigint`.

Also test the failure path once: delete a parent row in a copy of the source and run the copier — it
must report the orphans and exit non-zero with the schema empty.

## 5. Report

Per database: rows copied and verified, tables, orphans (0), sequences reset. Then hand-check a few
values on both sides (an id, a timestamp in ms, a boolean). "7 databases, 7984 rows, 0 differences"
is a claim someone can trust; "migration done" is not.

## Local gotcha

Docker on macOS via Colima only mounts `$HOME` into the VM. A bind mount from `/tmp` or `/private/tmp`
gives the container an **empty directory** — the app then happily creates a fresh empty database and
everything "works". Keep test data under `$HOME`.
