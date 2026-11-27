#!/bin/sh
# Dump one schema, verify it is readable, keep the last N, then prove it restores into a scratch DB.
# usage: pg_backup_verify.sh "postgresql://user:pass@host:port/db" <schema> <dir> [keep=14]
set -eu
DSN="$1"; SCHEMA="$2"; DIR="$3"; KEEP="${4:-14}"
case "$SCHEMA" in (*[!a-z0-9_]*|"") echo "bad schema name" >&2; exit 2;; esac
mkdir -p "$DIR/$SCHEMA"
OUT="$DIR/$SCHEMA/$SCHEMA-$(date -u +%Y-%m-%dT%H-%M).dump"
pg_dump "$DSN" -n "$SCHEMA" -Fc -Z 6 -f "$OUT.partial"
pg_restore --list "$OUT.partial" | grep -q "TABLE DATA" || { rm -f "$OUT.partial"; echo "dump unreadable" >&2; exit 1; }
mv "$OUT.partial" "$OUT"
# keep the newest $KEEP (portable: no GNU-only `head -n -N` / `xargs -r`)
COUNT=$(ls -1 "$DIR/$SCHEMA"/"$SCHEMA"-*.dump | wc -l)
EXCESS=$((COUNT - KEEP))
if [ "$EXCESS" -gt 0 ]; then
  ls -1 "$DIR/$SCHEMA"/"$SCHEMA"-*.dump | sort | head -n "$EXCESS" | while read -r OLD; do rm -f "$OLD"; done
fi

# Restore drill
SCRATCH="restore_check_$$"
ADMIN_DSN="${DSN%/*}/postgres"
psql "$ADMIN_DSN" -qc "create database $SCRATCH"
trap 'psql "$ADMIN_DSN" -qc "drop database if exists $SCRATCH" >/dev/null 2>&1' EXIT
pg_restore -d "${DSN%/*}/$SCRATCH" --no-owner "$OUT"
DIFF=0
for T in $(psql "$DSN" -tAc "select table_name from information_schema.tables where table_schema='$SCHEMA' and table_type='BASE TABLE'"); do
  A=$(psql "$DSN" -tAc "select count(*) from \"$SCHEMA\".\"$T\"")
  B=$(psql "${DSN%/*}/$SCRATCH" -tAc "select count(*) from \"$SCHEMA\".\"$T\"")
  [ "$A" = "$B" ] || { echo "DIFF $T: $A vs $B" >&2; DIFF=$((DIFF + 1)); }
done
[ "$DIFF" = 0 ] && echo "ok $OUT (restored and counts match)" || { echo "restore drill failed: $DIFF tables" >&2; exit 1; }
