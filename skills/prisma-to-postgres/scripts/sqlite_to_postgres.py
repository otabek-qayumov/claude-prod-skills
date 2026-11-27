#!/usr/bin/env python3
"""Copy SQLite databases into existing PostgreSQL schemas and prove nothing was lost.

usage: sqlite_to_postgres.py --dsn postgresql://u:p@host:port/db --db app.db:schema [--db other.db:schema2 ...]
       [--rename Model=table ...] [--skip-table _prisma_migrations]

The target tables must already exist (create them with your migrations first). Column types are read from
the target (information_schema), so the script needs no models. Names map with the same snake_case rule as
prisma_to_sqlalchemy.py.

Per schema, inside ONE transaction (any failure = nothing written):
  1. load every table with COPY, foreign-key triggers off (session_replication_role = replica, needs a
     superuser) so load order and FK cycles do not matter;
  2. read every table back and compare row count + an order-independent SHA-256 checksum with the source;
  3. check every foreign key for orphans (child rows pointing at a missing parent);
  4. move identity sequences past max(id).
Conversions: Prisma DateTime (epoch milliseconds as INTEGER, or text) -> timestamptz UTC; 0/1 -> boolean;
32-bit overflow, non-integer floats in int columns and NUL bytes in text fail loudly with the row number.

requires: pip install asyncpg
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import math
import re
import sqlite3
import sys
from datetime import UTC, datetime
from typing import Any

import asyncpg

RENAMES = {"User": "users"}
INT_RANGE = {"integer": (-(2**31), 2**31 - 1), "smallint": (-(2**15), 2**15 - 1), "bigint": (-(2**63), 2**63 - 1)}


def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s).lower()


def table_name(model: str) -> str:
    return RENAMES.get(model) or snake(model)


# ── conversions ─────────────────────────────────────────────────────────────


def to_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, int | float) or (isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v)):
        return datetime.fromtimestamp(float(v) / 1000, tz=UTC)
    s = str(v).strip().replace(" ", "T").replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def to_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "t"):
        return True
    if s in ("0", "false", "f"):
        return False
    raise ValueError(f"not a boolean: {v!r}")


def to_int(kind: str):  # type: ignore[no-untyped-def]
    lo, hi = INT_RANGE[kind]

    def conv(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, float) and not v.is_integer():
            raise ValueError(f"not an integer: {v!r}")
        n = int(v)
        if not lo <= n <= hi:
            raise ValueError(f"does not fit {kind}: {n}")
        return n

    return conv


def to_float(v: Any) -> float | None:
    return None if v is None else float(v)


def to_text(v: Any) -> str | None:
    if v is None:
        return None
    s = v if isinstance(v, str) else str(v)
    if "\x00" in s:
        raise ValueError("text contains a NUL byte (PostgreSQL rejects it)")
    return s


def converter(pg_type: str):  # type: ignore[no-untyped-def]
    if pg_type.startswith("timestamp"):
        return to_ts
    if pg_type == "boolean":
        return to_bool
    if pg_type in INT_RANGE:
        return to_int(pg_type)
    if pg_type in ("double precision", "real", "numeric"):
        return to_float
    return to_text


# ── checksum ────────────────────────────────────────────────────────────────


def canon(v: Any) -> str:
    if v is None:
        return "∅"
    if isinstance(v, bool):
        return "T" if v else "F"
    if isinstance(v, datetime):
        return "D" + str(round(v.timestamp() * 1000))
    if isinstance(v, float):
        return "R" + ("nan" if math.isnan(v) else repr(v))
    if isinstance(v, int):
        return "I" + str(v)
    return "S" + str(v)


def checksum(rows: Any) -> str:
    digests = sorted(hashlib.sha256("\x1f".join(canon(x) for x in r).encode()).hexdigest() for r in rows)
    return hashlib.sha256("".join(digests).encode()).hexdigest()


# ── copy one database ───────────────────────────────────────────────────────


async def copy_db(pg: asyncpg.Connection, path: str, schema: str, skip: set[str]) -> tuple[int, list[str]]:
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = [r[0] for r in src.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")
              if r[0] not in skip]
    target = {}
    for t, c, typ in await pg.fetch(
        "select table_name, column_name, data_type from information_schema.columns where table_schema=$1", schema
    ):
        target.setdefault(t, {})[c] = typ
    problems: list[str] = []
    total = 0
    async with pg.transaction():
        await pg.execute("SET LOCAL session_replication_role = replica")
        for t in tables:
            dst = table_name(t)
            if dst not in target:
                raise RuntimeError(f"{schema}.{dst}: table missing in target")
            src_cols = [r[1] for r in src.execute(f'pragma table_info("{t}")')]
            cols = [snake(c) for c in src_cols]
            missing = [c for c in cols if c not in target[dst]]
            if missing:
                raise RuntimeError(f"{schema}.{dst}: columns missing in target: {missing}")
            conv = [converter(target[dst][c]) for c in cols]
            rows = []
            select = ", ".join(f'"{c}"' for c in src_cols)
            for i, r in enumerate(src.execute(f'select {select} from "{t}"')):
                try:
                    rows.append(tuple(f(v) for f, v in zip(conv, r, strict=True)))
                except ValueError as e:
                    raise RuntimeError(f"{schema}.{dst} row {i}: {e}") from e
            if rows:
                await pg.copy_records_to_table(dst, records=rows, columns=cols, schema_name=schema)
            back = await pg.fetch(f'select {", ".join(chr(34) + c + chr(34) for c in cols)} from "{schema}"."{dst}"')
            if len(back) != len(rows) or checksum(tuple(x) for x in back) != checksum(rows):
                problems.append(f"{schema}.{dst}: read-back differs ({len(rows)} source rows, {len(back)} target)")
            total += len(rows)

        for tbl, col, ptbl, pcol in await pg.fetch(
            """select c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text, pa.attname
               from pg_constraint c
               join pg_namespace n on n.oid = c.connamespace
               join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
               join pg_attribute pa on pa.attrelid = c.confrelid and pa.attnum = c.confkey[1]
               where c.contype = 'f' and n.nspname = $1""",
            schema,
        ):
            n = await pg.fetchval(
                f'select count(*) from {tbl} b where b."{col}" is not null and not exists '
                f'(select 1 from {ptbl} p where p."{pcol}" = b."{col}")'
            )
            if n:
                problems.append(f"{tbl}.{col} -> {ptbl}: {n} orphan rows")

        for seq_tbl, seq_col in await pg.fetch(
            "select table_name, column_name from information_schema.columns "
            "where table_schema=$1 and (is_identity='YES' or column_default like 'nextval%')",
            schema,
        ):
            await pg.execute(
                f"select setval(pg_get_serial_sequence('\"{schema}\".\"{seq_tbl}\"', '{seq_col}'), "
                f'coalesce((select max("{seq_col}") from "{schema}"."{seq_tbl}"), 0) + 1, false)'
            )
        if problems:
            raise Verification(problems)
    return total, problems


class Verification(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--db", action="append", required=True, help="path.db:schema")
    ap.add_argument("--rename", action="append", default=[], help="Model=table")
    ap.add_argument("--skip-table", action="append", default=["_prisma_migrations"])
    a = ap.parse_args()
    for r in a.rename:
        k, v = r.split("=", 1)
        RENAMES[k] = v
    pg = await asyncpg.connect(a.dsn)
    failed = False
    try:
        for spec in a.db:
            path, schema = spec.rsplit(":", 1)
            try:
                n, _ = await copy_db(pg, path, schema, set(a.skip_table))
                print(f"ok   {schema}: {n} rows verified ({path})")
            except (Verification, RuntimeError) as e:
                failed = True
                print(f"FAIL {schema}: {e}")
    finally:
        await pg.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
