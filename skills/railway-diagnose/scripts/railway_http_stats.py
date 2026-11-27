#!/usr/bin/env python3
"""Summarise `railway logs --http --json` output: latency per route, status mix, slow requests.

usage: railway_http_stats.py http.jsonl [--slow-ms 5000]
"""

import collections
import json
import re
import sys

STATIC = re.compile(r"^/_next/static|\.(png|jpe?g|svg|ico|woff2?|css|js|webp|mp4|map)(\?|$)")


def pct(values: list[int], q: float) -> int:
    v = sorted(values)
    return v[int(q * (len(v) - 1))] if v else 0


def route(path: str) -> str:
    p = path.split("?")[0]
    p = re.sub(r"/c[0-9a-z]{20,}", "/:id", p)  # cuid
    p = re.sub(r"/[0-9a-f-]{24,}", "/:id", p)  # uuid / hex ids
    return re.sub(r"/\d+", "/:n", p)


def main() -> None:
    path = sys.argv[1]
    slow_ms = int(sys.argv[sys.argv.index("--slow-ms") + 1]) if "--slow-ms" in sys.argv else 5000
    rows = [json.loads(line) for line in open(path) if line.startswith("{")]
    rows.sort(key=lambda r: r["timestamp"])
    if not rows:
        sys.exit("no rows")
    dyn = [r for r in rows if not STATIC.search(r["path"])]
    d = [r["totalDuration"] for r in dyn]
    print(f"{len(rows)} requests ({rows[0]['timestamp'][:16]} → {rows[-1]['timestamp'][:16]}), {len(dyn)} dynamic")
    print(f"dynamic: p50={pct(d, .5)} p90={pct(d, .9)} p99={pct(d, .99)} max={max(d) if d else 0} ms\n")

    by = collections.defaultdict(list)
    for r in dyn:
        by[(r["method"], route(r["path"]))].append(r["totalDuration"])
    print(f"{'count':>6} {'p50':>7} {'p90':>7} {'max':>8}  route (slowest p90 first)")
    for (m, p), v in sorted(by.items(), key=lambda kv: -pct(kv[1], .9))[:25]:
        print(f"{len(v):>6} {pct(v, .5):>7} {pct(v, .9):>7} {max(v):>8}  {m} {p[:80]}")

    print("\nstatus:", dict(collections.Counter(r["httpStatus"] for r in rows)))
    hosts = collections.Counter(r.get("host", "") for r in rows).most_common(8)
    print("hosts:", hosts)
    up = [r for r in rows if r.get("upstreamErrors")]
    print(f"upstream errors: {len(up)}")
    slow = [r for r in dyn if r["totalDuration"] > slow_ms]
    print(f"\nslower than {slow_ms} ms: {len(slow)}")
    for r in slow[-30:]:
        print(f"  {r['timestamp'][5:19]} {r['totalDuration']:>7} {r['httpStatus']} {r['method']} {r['path'][:70]}")


if __name__ == "__main__":
    main()
