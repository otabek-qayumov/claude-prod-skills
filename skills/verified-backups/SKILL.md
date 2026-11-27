---
name: verified-backups
description: Set up backups that are proven restorable — PostgreSQL per-schema pg_dump with a restore drill, atomic SQLite snapshots, offsite copies including uploaded files. Use when adding or auditing backups, before any migration or cutover, or when someone asks "is the data safe?".
---

# A backup is a restore you have already done

Untested backups fail in the ways nobody looks at: truncated files, the wrong schema, a dump made by
an older client, files (videos, uploads) that were never in the database dump. Prove the restore.

## Before any risky change: full snapshot, verified

1. Code: `git clone --mirror` + `git bundle create all.bundle --all` + `git bundle verify`.
2. Configuration/secrets: export environment variables to a file with mode 600, outside any repo.
   Never echo values into logs or chat.
3. Data: databases **and** the file volume. Compare the file list (size + path) on the server with the
   local copy; check each database with `PRAGMA integrity_check` / `pg_restore --list`.

## PostgreSQL: one dump per schema

`scripts/pg_backup_verify.sh <dsn> <schema> <dir>`:
- `pg_dump -n <schema> -Fc` to `*.dump.partial`, then `pg_restore --list` must succeed and contain
  `TABLE DATA`, then rename to `*.dump` — a crash never leaves a half file posing as the latest backup;
- keep the last N per schema; run nightly (cron, Celery beat);
- client major version ≥ server major version (install `postgresql-client-16` from PGDG in images).

Restore drill (put it in CI): create a scratch database, `pg_restore --no-owner` the dump, compare
`count(*)` of every table with the source, count foreign keys, drop the scratch database.

## SQLite: consistent snapshots

Never copy a live SQLite file. Use `VACUUM INTO '<path>.partial'`, then rename. A plain copy during a
write can be corrupt; an interrupted `VACUUM INTO` without the temp name becomes "today's backup" and
gets shipped offsite.

## Offsite

Upload the latest snapshot to S3-compatible storage (R2, Railway bucket) with a marker file so the same
file is not re-uploaded hourly; keep 30. **Include uploaded files** (videos, documents, voice notes):
upload new/changed files only (name + size), stream them (no full read into memory), never delete
remotely when the local copy disappears — the backup must survive an accidental delete.

## Report

What is backed up, where, how often, how many are kept, when a restore was last proven, and what is
NOT covered (e.g. "videos only on the server disk" is a finding, not a footnote).
