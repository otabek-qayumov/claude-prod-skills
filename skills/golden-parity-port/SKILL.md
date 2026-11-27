---
name: golden-parity-port
description: Rewrite a codebase in another language or framework (e.g. TypeScript/Next.js → Python/FastAPI) without changing a single user-visible text or business rule. Use when porting, re-platforming or "rewriting in X" a live product, or when the user says texts and logic must not break.
---

# Port without changing behaviour

A rewrite of a live product succeeds only if users cannot tell. Treat the old code as the
specification and make every claim of "same behaviour" a test that compares against it.

## Rules

1. **Texts are data, never retyped.** Export dictionaries, message templates and translations from
   the old code by *executing* it (e.g. `npx tsx export.ts`), not by parsing source or copying by hand.
   Old and new frontends/backends then read the same JSON.
2. **Logic is pinned by golden samples.** For each pure function you port, generate inputs, run the
   *old* implementation, save `{input, output}` pairs as fixtures, and assert the new implementation
   returns byte-identical output. Thousands of samples are cheap; one mismatch is a bug.
3. **The old test suite is the contract.** Port the old tests alongside the code, not afterwards.
4. **No improvements during the port.** A bug you "fix" while porting is a behaviour change nobody
   reviewed. Record it, port it as-is, fix it later in its own change.
5. **Strangler, not big bang.** The old system keeps running; move one area (or one tenant) at a time,
   each with its own verification and a way back.

## Golden fixture exporter (TypeScript → JSON)

```ts
// export.ts — run inside the OLD repo: npx tsx export.ts out/
import { writeFileSync } from "node:fs";
import { translate } from "./src/lib/i18n";          // the real function, not a copy
const cases = [];
for (const key of Object.keys(DICTIONARY)) {
  const vars = Object.fromEntries([...key.matchAll(/\{(\w+)\}/g)].map((m, i) => [m[1], i % 2 ? i + 7 : `«${m[1]}»`]));
  for (const lang of ["uz", "ru"]) cases.push({ lang, key, vars, out: translate(lang, key, vars) });
}
writeFileSync(process.argv[2] + "/i18n.json", JSON.stringify(cases));
```

```python
# test_i18n.py — in the NEW repo
def test_matches_old_implementation():
    bad = [c for c in CASES if translate(c["lang"], c["key"], c["vars"]) != c["out"]]
    assert not bad, f"{len(bad)} mismatches, first: {bad[0]}"
```

Cover the edges deliberately: missing keys, missing variables, context-suffixed keys, empty strings,
numbers in templates.

## Semantics that silently differ (seen in real ports)

| Old (JS/TS) | Naive Python | Correct |
|---|---|---|
| `/\w/` is ASCII-only | `\w` matches Unicode | `re.compile(..., re.ASCII)` |
| `String(7.0)` → `"7"` | `str(7.0)` → `"7.0"` | format integral floats as ints |
| `a ?? b` (only null/undefined) | `a or b` (also `""`, `0`) | explicit `is None` / `in dict` checks |
| `!{}` is `false` | `not {}` is `True` | compare to `None`, not truthiness |
| Node `scryptSync(pin, saltHex, 32)` uses the hex **string** as salt | `bytes.fromhex(salt)` | `salt=salt_hex.encode()`, N=16384 r=8 p=1 |
| `Intl.DateTimeFormat(..., {timeZone})` | naive datetimes | explicit zone, compare rendered strings |
| `Math.round(-0.5)` → `-0` | `round(-0.5)` → `-0` (banker's for .5!) | test halves explicitly |

Hashes are the easiest place to lock users out: export real hashes created by the old code for known
inputs and verify them in the new code before touching the login flow.

## Inventory and progress

Generate the list of things to port from the old code (server actions, routes, pages, jobs) into a
checklist file and tick items only when their parity test passes. Report progress as numbers
("14 496/14 496 samples equal; 3 of 8 phases done"), not adjectives.
