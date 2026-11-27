#!/usr/bin/env python3
"""Generate SQLAlchemy 2 models (Mapped / mapped_column) from a Prisma schema, PostgreSQL-style.

usage: prisma_to_sqlalchemy.py schema.prisma out.py [--rename Model=table ...] [--id-func module:func]

- Names become snake_case (`VideoCopy.createdAt` -> `video_copy.created_at`); reserved words are renamed
  (`User` -> `users` by default).
- Prisma's own defaults are kept: a relation without `onDelete` is RESTRICT when required and SET NULL
  when optional; `onUpdate` is CASCADE. These match the SQL Prisma generated for SQLite.
- `///` doc comments become table/column comments in PostgreSQL.
- Foreign keys inside a dependency cycle (A -> B -> C -> A) get `use_alter=True`. NOTE: Alembic's
  `op.create_table` silently drops those constraints — add them with `op.create_foreign_key` after the
  tables (see SKILL.md).
- Supported: scalar String/Int/Float/Boolean/DateTime, single-column @id/@unique/relations, @@index,
  @@unique, @default(cuid()/now()/autoincrement()/literal), @updatedAt. Anything else raises loudly.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RENAMES = {"User": "users"}
ID_FUNC = "app.ids:new_id"

SCALAR = {"String", "Int", "Float", "Boolean", "DateTime"}
SA_TYPE = {"String": "Text", "Int": "Integer", "Float": "Double", "Boolean": "Boolean", "DateTime": "DateTime(timezone=True)"}
PY_TYPE = {"String": "str", "Int": "int", "Float": "float", "Boolean": "bool", "DateTime": "datetime"}


def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s).lower()


def table_name(model: str) -> str:
    return RENAMES.get(model) or snake(model)


def index_name(kind: str, table: str, cols: list[str]) -> str:
    name = f"{kind}_{table}_{'_'.join(cols)}"
    return name if len(name) <= 63 else name[:54] + "_" + hashlib.sha1(name.encode()).hexdigest()[:8]


@dataclass
class Field:
    name: str
    type: str
    optional: bool
    is_list: bool
    attrs: str
    doc: list[str] = field(default_factory=list)


@dataclass
class Model:
    name: str
    fields: list[Field] = field(default_factory=list)
    block: list[str] = field(default_factory=list)
    doc: list[str] = field(default_factory=list)


def parse(text: str) -> dict[str, Model]:
    models: dict[str, Model] = {}
    cur: Model | None = None
    doc: list[str] = []
    for raw in text.splitlines():
        q = raw.strip()
        if q.startswith("///"):
            doc.append(q[3:].strip())
            continue
        if cur is None:
            m = re.match(r"^model\s+(\w+)\s*\{", q)
            if m:
                cur = models[m.group(1)] = Model(m.group(1), doc=doc)
            doc = []
            continue
        if q == "}":
            cur, doc = None, []
            continue
        if not q or q.startswith("//"):
            continue
        if q.startswith("@@"):
            cur.block.append(q)
            doc = []
            continue
        m = re.match(r"^(\w+)\s+(\w+)(\[\])?(\?)?\s*(.*)$", q)
        if not m:
            raise ValueError(f"{cur.name}: cannot parse: {q}")
        attrs = re.sub(r"\s//.*$", "", m.group(5))
        cur.fields.append(Field(m.group(1), m.group(2), bool(m.group(4)), bool(m.group(3)), attrs, doc))
        doc = []
    return models


def arg(attrs: str, name: str) -> str | None:
    """Inner text of `@name(...)`, honouring nested parentheses."""
    i = attrs.find(name + "(")
    if i < 0:
        return None
    j = k = i + len(name) + 1
    depth = 1
    while depth:
        depth += {"(": 1, ")": -1}.get(attrs[k], 0)
        k += 1
    return attrs[j : k - 1]


def names(s: str) -> list[str]:
    return [x.strip() for x in s.strip("[] ").split(",") if x.strip()]


def cycles(edges: dict[str, set[str]]) -> set[tuple[str, str]]:
    """Edges (a, b) that lie inside a strongly connected component of size > 1 (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    comp: dict[str, int] = {}
    n = 0

    def visit(v: str) -> None:
        nonlocal n
        index[v] = low[v] = n
        n += 1
        stack.append(v)
        on.add(v)
        for w in edges[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on.discard(w)
                comp[w] = index[v]
                if w == v:
                    break

    for v in edges:
        if v not in index:
            visit(v)
    size: dict[int, int] = {}
    for c in comp.values():
        size[c] = size.get(c, 0) + 1
    return {(a, b) for a in edges for b in edges[a] if comp[a] == comp[b] and size[comp[a]] > 1}


def generate(models: dict[str, Model]) -> str:
    fks: dict[tuple[str, str], tuple[str, str, str]] = {}
    for mo in models.values():
        for f in mo.fields:
            if f.type in SCALAR or f.is_list:
                continue
            r = arg(f.attrs, "@relation")
            if r is None or "fields:" not in r:
                continue
            src = names(re.search(r"fields:\s*(\[[^\]]*\])", r).group(1))  # type: ignore[union-attr]
            dst = names(re.search(r"references:\s*(\[[^\]]*\])", r).group(1))  # type: ignore[union-attr]
            if len(src) != 1 or len(dst) != 1:
                raise ValueError(f"{mo.name}.{f.name}: composite foreign keys are not supported")
            od = re.search(r"onDelete:\s*(\w+)", r)
            action = od.group(1) if od else ("SetNull" if f.optional else "Restrict")
            sql = {"Cascade": "CASCADE", "SetNull": "SET NULL", "Restrict": "RESTRICT", "NoAction": "NO ACTION"}[action]
            fks[(mo.name, src[0])] = (table_name(f.type), snake(dst[0]), sql)

    edges: dict[str, set[str]] = {}
    for (model, _), (target, _, _) in fks.items():
        if table_name(model) != target:
            edges.setdefault(table_name(model), set()).add(target)
            edges.setdefault(target, set())
    in_cycle = cycles(edges)

    mod, func = ID_FUNC.split(":")
    out = [
        '"""Generated from schema.prisma by prisma_to_sqlalchemy.py — edit the Prisma schema, then regenerate."""',
        "",
        "from datetime import datetime",
        "",
        "from sqlalchemy import Boolean, DateTime, Double, ForeignKey, Identity, Index, Integer, Text, UniqueConstraint",
        "from sqlalchemy import text as sql",
        "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column",
        "",
        f"from {mod} import {func}",
        "",
        "",
        "class Base(DeclarativeBase):",
        "    pass",
        "",
    ]
    for mo in models.values():
        tbl = table_name(mo.name)
        out += ["", f"class {mo.name}(Base):", f"    __tablename__ = {tbl!r}"]
        args: list[str] = []
        for b in mo.block:
            cols = [snake(c) for c in names(re.search(r"\(\s*(\[[^\]]*\])", b).group(1))]  # type: ignore[union-attr]
            if b.startswith("@@index"):
                args.append(f"Index({index_name('ix', tbl, cols)!r}, {', '.join(map(repr, cols))})")
            elif b.startswith("@@unique"):
                args.append(f"UniqueConstraint({', '.join(map(repr, cols))}, name={index_name('uq', tbl, cols)!r})")
            else:
                raise ValueError(f"{mo.name}: unsupported block attribute: {b}")
        if mo.doc:
            args.append(f"{{'comment': {' '.join(mo.doc)!r}}}")
        if args:
            out.append(f"    __table_args__ = ({', '.join(args)}{',' if len(args) == 1 else ''})")
        for f in mo.fields:
            if f.type not in SCALAR:
                continue
            if f.is_list:
                raise ValueError(f"{mo.name}.{f.name}: scalar lists are not supported")
            col, a = snake(f.name), f.attrs
            parts, kw = [SA_TYPE[f.type]], []
            if (mo.name, f.name) in fks:
                tgt, tcol, act = fks[(mo.name, f.name)]
                alter = ", use_alter=True" if (tbl, tgt) in in_cycle else ""
                parts.append(f"ForeignKey({f'{tgt}.{tcol}'!r}, ondelete={act!r}, onupdate='CASCADE'{alter})")
            d = arg(a, "@default")
            if re.search(r"@id\b", a):
                kw.append("primary_key=True")
                if d == "autoincrement()":
                    parts.append("Identity(always=False)")
            if d is not None and d != "autoincrement()":
                if d == "cuid()":
                    kw.append(f"default={func}")
                elif d == "now()" or d in ("true", "false") or re.fullmatch(r"-?\d+(\.\d+)?", d):
                    kw.append(f"server_default=sql({d!r})")
                elif d.startswith('"'):
                    kw.append(f"server_default={d[1:-1]!r}")
                else:
                    raise ValueError(f"{mo.name}.{f.name}: unsupported @default({d})")
            if "@updatedAt" in a:
                kw += ["server_default=sql('now()')", "onupdate=sql('now()')"]
            if re.search(r"@unique\b", a):
                kw.append("unique=True")
            kw.append(f"nullable={f.optional}")
            if f.doc:
                kw.append(f"comment={' '.join(f.doc)!r}")
            py = PY_TYPE[f.type] + (" | None" if f.optional else "")
            out.append(f"    {col}: Mapped[{py}] = mapped_column({', '.join([repr(col), *parts, *kw])})")
    return "\n".join(out) + "\n"


def main() -> None:
    global ID_FUNC
    args = sys.argv[1:]
    while "--rename" in args:
        i = args.index("--rename")
        model, table = args[i + 1].split("=", 1)
        RENAMES[model] = table
        del args[i : i + 2]
    if "--id-func" in args:
        i = args.index("--id-func")
        ID_FUNC = args[i + 1]
        del args[i : i + 2]
    src, dst = Path(args[0]), Path(args[1])
    models = parse(src.read_text())
    dst.write_text(generate(models))
    print(f"{len(models)} models -> {dst}")


if __name__ == "__main__":
    main()
